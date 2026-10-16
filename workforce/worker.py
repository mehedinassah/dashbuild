import json
from ollama import chat as _ollama_chat

from .config import CFG


def chat(**kw):
    """Ollama chat. Put "think": false in config.json for thinking models such as qwen3."""
    if "think" in CFG:
        kw["think"] = CFG["think"]
    return _ollama_chat(**kw)


def first_json_call(text):
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and "name" in obj and isinstance(obj.get("arguments"), dict):
                return obj["name"], obj["arguments"]
        except ValueError:
            pass
        i = text.find("{", i + 1)
    return None


def run_worker(*, model, system, task, tools, state,
               max_steps=CFG["max_steps"], require_tests=True, num_ctx=CFG["num_ctx"],
               finish_check=None):
    table = {f.__name__: f for f in tools}
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task}]
    recent = []

    for step in range(1, max_steps + 1):
        if state.get("abort"):
            print("CONTROLLER: giving up this attempt:", str(state["abort"])[:200])
            return {"status": "aborted", "steps": step - 1, "files": sorted(state["written"])}
        print(f"\n--- step {step} ---")
        resp = chat(model=model, messages=messages, tools=tools,
                    options={"num_ctx": num_ctx, "temperature": CFG["temperature"],
                             "num_predict": CFG["num_predict"], "repeat_penalty": 1.1})
        msg = resp.message
        if getattr(resp, "done_reason", None) == "length":
            print("CONTROLLER: reply hit the length limit and was discarded")
            messages.append({"role": "user", "content":
                "Your last reply was far too long and was cut off. Make a "
                "smaller, simpler step: one tool call, with short content."})
            continue
        call = None

        if msg.tool_calls:
            c = msg.tool_calls[0]  # one call at a time
            call = (c.function.name, dict(c.function.arguments))
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [c]})
        else:
            call = first_json_call(msg.content or "")
            if call:
                messages.append({"role": "assistant",
                                 "content": json.dumps({"name": call[0], "arguments": call[1]})})

        if call is None:
            problems = []
            if require_tests:
                if not state["written"]:
                    problems.append("you have not written any files yet")
                if not state["tests_passed"]:
                    problems.append("tests have not passed since your last change; call run_tests")
            if state.get("undefined"):
                problems.append("fix these undefined names first: " + "; ".join(
                    f"{k}: {v}" for k, v in state["undefined"].items()))
            if finish_check:
                problems += list(finish_check())
            if not problems:
                print("DONE:", (msg.content or "")[:300])
                return {"status": "done", "summary": msg.content, "steps": step,
                        "files": sorted(state["written"])}
            print("CONTROLLER:", "; ".join(problems))
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({"role": "user", "content":
                             "You cannot finish yet: " + "; ".join(problems) +
                             ". Use the tools."})
            continue

        name, args = call
        print(f"TOOL: {name} {list(args)}")

        key = (name, json.dumps(args, sort_keys=True))
        recent.append(key)
        if recent[-3:].count(key) == 3:
            result = "ERROR: you repeated this exact call 3 times. Do something different."
        elif name not in table:
            result = f"ERROR: unknown tool {name}. Available: {list(table)}"
        else:
            try:
                result = str(table[name](**args))
            except Exception as e:
                result = f"ERROR: {e}"

        print("  ->", result[:300].replace("\n", "\n     "))
        messages.append({"role": "tool", "tool_name": name, "content": result})

    return {"status": "max_steps", "steps": max_steps, "files": sorted(state["written"])}
