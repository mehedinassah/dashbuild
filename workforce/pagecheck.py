"""Page check: after a change, load every page that needs no arguments in a throw-away test database
and look for the things no unit test notices: server errors, unrendered template tags, and raw Python
text (tuples, dicts, QuerySet, 'None') printed on the page. Plain Python decides, no model."""
import json
import os
import subprocess
import sys

MARK = "PAGECHECK:"

SCRIPT = r'''
import json, re
from django.test import Client
from django.test.runner import DiscoverRunner
from django.urls import get_resolver, URLResolver

Q = r"(?:'|&#x27;|&quot;)"
BAD = [
    ("a Python error page", r"Traceback \(most recent call last\)|TemplateSyntaxError|NoReverseMatch|TemplateDoesNotExist"),
    ("an unrendered template tag", r"\{\{|\{%"),
    ("raw Python tuple text", r"\(" + Q + r"\w+" + Q + r", "),
    ("raw Python dict or list text", r"\{" + Q + r"\w+" + Q + r": |\[\{" + Q),
    ("raw Python object text", r"&lt;QuerySet|&lt;bound method|&lt;function |object at 0x|Decimal\(" + Q),
    ("the word None printed as content", r">\s*None\s*<"),
]

def walk(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from walk(p.url_patterns, prefix + str(p.pattern))
        else:
            yield prefix + str(p.pattern)

runner = DiscoverRunner(verbosity=0, interactive=False)
runner.setup_test_environment()
old = runner.setup_databases()
problems = []
try:
    c = Client(raise_request_exception=False)
    for route in sorted(set(walk(get_resolver().url_patterns))):
        if re.search(r"[<(\[\^$*+?\\]", route) or route.startswith(("admin", "static", "media")):
            continue
        r = c.get("/" + route)
        if r.status_code >= 500:
            problems.append(f"GET /{route}: server error {r.status_code}")
            continue
        if r.status_code != 200 or "html" not in r.get("Content-Type", ""):
            continue
        html = r.content.decode("utf-8", "replace")
        for what, pat in BAD:
            m = re.search(pat, html)
            if m:
                problems.append(f"GET /{route}: {what} ('{html[max(0, m.start()-20):m.end()+30].strip()[:70]}')")
                break
finally:
    runner.teardown_databases(old)
    runner.teardown_test_environment()
print("@MARK@" + json.dumps(problems))
'''.replace("@MARK@", MARK)


def check(ws):
    """-> list of problem strings, or None when the check could not run (it never blocks on its own failure)."""
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        r = subprocess.run([sys.executable, "manage.py", "shell", "-c", SCRIPT], cwd=ws, capture_output=True,
                           text=True, env=env, timeout=240)
    except (subprocess.TimeoutExpired, OSError):
        return None
    for line in reversed((r.stdout or "").splitlines()):
        if line.startswith(MARK):
            try:
                return json.loads(line[len(MARK):])
            except ValueError:
                return None
    return None


def new_problems(before, after):
    """Only what the change introduced. When either check could not run, nothing is reported."""
    if before is None or after is None:
        return []
    return [p for p in after if p not in before]
