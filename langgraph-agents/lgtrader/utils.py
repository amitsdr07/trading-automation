from __future__ import annotations
from datetime import datetime, timezone, timedelta
import yaml, os

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist() -> datetime:
    return datetime.now(tz=IST)

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_app_config() -> dict:
    p = os.environ.get("PATH_CONFIG") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
    return load_yaml(p)
