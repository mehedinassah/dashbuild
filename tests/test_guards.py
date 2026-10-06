import json
import pytest
from workforce.tools import make_tools, python_problem


def build(tmp_path, cfg=None):
    if cfg is not None:
        (tmp_path / ".workforce.json").write_text(json.dumps(cfg))
    state = {}
    tools = {f.__name__: f for f in make_tools(tmp_path, state)}
    return tools, state


TWO_TESTS = "def test_one():\n    pass\n\ndef test_two():\n    pass\n"


def test_path_escape_blocked(tmp_path):
    t, _ = build(tmp_path)
    with pytest.raises(ValueError):
        t["read_file"]("../secret.txt")


def test_cannot_delete_existing_tests(tmp_path):
    t, _ = build(tmp_path)
    (tmp_path / "test_a.py").write_text(TWO_TESTS)
    assert t["write_file"]("test_a.py", "def test_one():\n    pass\n").startswith("REJECTED")


def test_cannot_shrink_file(tmp_path):
    t, _ = build(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n" * 12)
    assert t["write_file"]("a.py", "x = 1\n").startswith("REJECTED")


def test_invalid_python_rejected(tmp_path):
    t, _ = build(tmp_path)
    assert t["write_file"]("a.py", "def f(:\n").startswith("REJECTED")


def test_duplicate_definition_rejected(tmp_path):
    t, _ = build(tmp_path)
    assert t["write_file"]("a.py", "def f():\n    pass\n\ndef f():\n    pass\n").startswith("REJECTED")


def test_append_keeps_old_tests(tmp_path):
    t, _ = build(tmp_path)
    (tmp_path / "test_a.py").write_text("def test_one():\n    pass\n")
    assert t["append_file"]("test_a.py", "def test_two():\n    pass\n").startswith("Wrote")
    text = (tmp_path / "test_a.py").read_text()
    assert "test_one" in text and "test_two" in text


def test_edit_file_empty_old_text_rejected(tmp_path):
    t, _ = build(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n")
    assert t["edit_file"]("a.py", "", "y = 2\n").startswith("ERROR")


def test_protected_config(tmp_path):
    t, _ = build(tmp_path)
    assert t["write_file"](".workforce.json", "{}").startswith("REJECTED")


def test_template_extends_missing_file(tmp_path):
    t, _ = build(tmp_path)
    assert t["write_file"]("t.html", "{% extends 'base.html' %}").startswith("REJECTED")


def test_template_extends_existing_file(tmp_path):
    t, _ = build(tmp_path)
    t["write_file"]("base.html", "<html></html>")
    assert t["write_file"]("t.html", "{% extends 'base.html' %}").startswith("Wrote")


def test_undefined_name_warns_and_is_tracked(tmp_path):
    t, state = build(tmp_path)
    assert "WARNING" in t["write_file"]("a.py", "x = foo\n")
    assert state["undefined"]
    t["write_file"]("a.py", "foo = 1\nx = foo\n")
    assert not state["undefined"]


def test_run_command_allow_list(tmp_path):
    t, _ = build(tmp_path, {"commands": [["python", "--version"]]})
    assert t["run_command"]("python --version").startswith("exit code 0")
    assert t["run_command"]("rm -rf .").startswith("REJECTED")
    assert t["run_command"]("python --version && ls").startswith("REJECTED")
    assert t["run_command"]("python -c print(1)").startswith("REJECTED")


def test_python_problem_helper():
    assert python_problem("from a import b\nfrom a import b\n")
    assert python_problem("class A: pass\nclass A: pass\n")
    assert python_problem("from a import b class A: pass")
    assert python_problem("x = 1\n") is None
