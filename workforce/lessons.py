"""Lessons: what went wrong on earlier cards, kept in .autopilot/lessons.json and shown to the model on
later cards. Python turns a failure into one general sentence (never copies card-specific output), counts
how often each one happens, and hands the most frequent few to the next prompt."""
import json
import re
from pathlib import Path

RULES = [
    (r"too weak",
     "Test the exact boundary of every number and comparison in the rule: the value itself, one below and "
     "one above. Also make one call that relies on a default argument."),
    (r"same failure happened|tests were wrong|contradict",
     "Work out each expected value from the records your own test creates. Never expect a count, total or "
     "text that the set-up does not produce."),
    (r"mock|patch",
     "Do not use mocks or patches. Create real objects with Model.objects.create and call the real code."),
    (r"does not check anything",
     "Every test method needs an assertEqual (or assertRaises) with an exact expected value."),
    (r"never mentions that|invalid input the rule never mentions|do not invent|do not use assertRaises",
     "Test only what the rule says. Do not invent errors, invalid inputs, messages or extra behaviour."),
    (r"expected \d+ tests to run",
     "Put every test in the one test class of the locked file; do not create extra test files or classes "
     "outside it."),
    (r"is not defined in",
     "Define the function with exactly the name given in the card."),
    (r"pages stopped working|page check",
     "After your change every page must still render without errors or raw Python text on it."),
    (r"METHOD|plain function",
     "Methods are called on an object with parentheses; plain functions are called by name."),
]


def lesson_from(text):
    """One general sentence for a failure message, or None when it is not worth remembering."""
    for pat, sentence in RULES:
        if re.search(pat, text or "", re.I):
            return sentence
    return None


def _path(ws):
    return Path(ws) / ".autopilot" / "lessons.json"


def _load(ws):
    try:
        return json.loads(_path(ws).read_text())
    except (OSError, ValueError):
        return {}


def learn(ws, text):
    """Remember the general lesson behind this failure text. -> the lesson or None."""
    sentence = lesson_from(text)
    if not sentence:
        return None
    data = _load(ws)
    data[sentence] = data.get(sentence, 0) + 1
    p = _path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.parent / ".gitignore").write_text("*\n")
    p.write_text(json.dumps(data, indent=1))
    return sentence


def relevant(ws, limit=4, max_chars=700):
    """The most frequent lessons as a prompt block, or an empty string."""
    data = _load(ws)
    if not data:
        return ""
    lines, used = [], 0
    for sentence, _n in sorted(data.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]:
        if used + len(sentence) > max_chars:
            break
        lines.append("- " + sentence)
        used += len(sentence)
    return "\nLessons learned on earlier cards of this project (follow them):\n" + "\n".join(lines) + "\n"
