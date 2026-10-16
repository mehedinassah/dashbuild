"""Deterministic page wiring for view cards. The model writes the view and its tests; Python does the
mechanical parts: the URL route, the message area in the layout, and the button on the list page."""
import ast
import re
from pathlib import Path

URL_RE = re.compile(r"^(<int:pk>/)?[a-z][a-z0-9_-]*/$")
LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ]{0,19}$")
SHOW_IF_RE = re.compile(r"^(not )?item\.\w+( (==|!=) (True|False|\d+|'[\w ]*'))?$")

MESSAGES_HTML = ('{% if messages %}<div class="messages">{% for m in messages %}'
                 '<div class="message {{ m.tags }}">{{ m }}</div>{% endfor %}</div>{% endif %}')
CSS = (".messages{margin:0 0 1rem}.message{padding:.7rem 1rem;border-radius:8px;margin-bottom:.5rem;"
       "background:var(--surface);border-left:4px solid var(--accent)}"
       ".message.error{border-left-color:#ef4444}.message.success{border-left-color:#22c55e}"
       "form.inline{display:inline}")


def check_view_card(c):
    """-> error text or None, for the extra fields a view card carries."""
    if c.get("class"):
        if not re.fullmatch(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*", c.get("url_name") or ""):
            return "a card that adds a method to a view class needs url_name, for example 'sales:create'"
        return None
    if not URL_RE.match(c.get("url") or ""):
        return "url must look like '<int:pk>/confirm/' or 'export/' (no leading slash, ends with /)"
    if c.get("button") and not LABEL_RE.match(c["button"]):
        return "button must be 1-20 letters, digits or spaces"
    if c.get("show_if") and not SHOW_IF_RE.match(c["show_if"]):
        return "show_if must look like: not item.confirmed   or   item.confirmed == True"
    if c.get("button") and "<int:pk>" not in c["url"]:
        return "a row button needs a url with <int:pk>/"
    return None


def wire_url(ws, app, url, view_name):
    """Add path(url, views.<view_name>, name=<view_name>) to <app>/urls.py. -> error or None"""
    p = Path(ws) / app / "urls.py"
    if not p.exists():
        return f"{app}/urls.py does not exist"
    src = p.read_text()
    if f'name="{view_name}"' in src or f"name='{view_name}'" in src:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return f"{app}/urls.py is not valid Python"
    lst = next((n.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.List)
                and any(getattr(t, "id", "") == "urlpatterns" for t in n.targets)), None)
    if lst is None:
        return f"no urlpatterns list in {app}/urls.py"
    lines = src.splitlines()
    end = lst.end_lineno - 1  # line holding the closing bracket
    lines[end:end] = [f'    path("{url}", views.{view_name}, name="{view_name}"),']
    new = "\n".join(lines).rstrip("\n") + "\n"
    try:
        ast.parse(new)
    except SyntaxError:
        return "the route could not be added safely"
    p.write_text(new)
    return None


def _find_layout(ws):
    for p in sorted(Path(ws).glob("*/templates/*/base.html")):
        if "{% block content %}" in p.read_text() and "{% extends" not in p.read_text():
            return p
    return None


def ensure_messages_block(ws):
    """Show Django messages above the page content. -> {path: original_text} of files changed"""
    p = _find_layout(ws)
    if p is None:
        return {}
    src = p.read_text()
    if 'class="messages"' in src:
        return {}
    marker = "{% block content %}"
    i = src.index(marker)
    start = src.rfind("\n", 0, i) + 1
    indent = re.match(r"\s*", src[start:i]).group(0)
    new = src[:start] + indent + MESSAGES_HTML + "\n" + src[start:]
    if "</style>" in new:
        new = new.replace("</style>", "    " + CSS + "\n  </style>", 1)
    p.write_text(new)
    return {p: src}


def add_row_button(ws, app, view_name, label, show_if=""):
    """Put a POST button in the 'actions' cell of every row of <app>'s list page."""
    p = Path(ws) / app / "templates" / app / "list.html"
    if not p.exists():
        return {}
    src = p.read_text()
    if f"{app}:{view_name}" in src or '<td class="actions">' not in src:
        return {}
    form = (f"<form method=\"post\" action=\"{{% url '{app}:{view_name}' item.pk %}}\" class=\"inline\">"
            f"{{% csrf_token %}}<button type=\"submit\" class=\"btn secondary\">{label}</button></form> ")
    if show_if:
        form = "{% if " + show_if + " %}" + form + "{% endif %}"
    new = src.replace('<td class="actions">', '<td class="actions">' + form, 1)
    p.write_text(new)
    return {p: src}


def apply(ws, card):
    """Everything a passed view card changes outside views.py. -> {path: original_text}"""
    changed = ensure_messages_block(ws)
    if card.get("button") and card.get("url"):
        changed.update(add_row_button(ws, card["app"], card["name"], card["button"], card.get("show_if", "")))
    return changed
