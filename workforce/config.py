import json
from pathlib import Path

DEFAULTS = {
    "model": "qwen2.5:7b",
    "max_steps": 15,
    "max_attempts": 3,
    "num_ctx": 8192,
    "num_predict": 2048,
    "temperature": 0.2,
}


def load():
    cfg = dict(DEFAULTS)
    p = Path(__file__).parent.parent / "config.json"
    if p.exists():
        cfg.update(json.loads(p.read_text()))
    return cfg


CFG = load()
