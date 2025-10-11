from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime, timedelta
from .utils import IST, now_ist

def _aggregate_1m_to_tf(bars_1m: List[dict], seconds: int) -> List[dict]:
    if not bars_1m: return []
    if seconds <= 60: return bars_1m
    # Assume bars_1m are in chronological order; aggregate by chunk size
    step = max(1, seconds // 60)
    out = []
    for i in range(0, len(bars_1m), step):
        chunk = bars_1m[i:i+step]
        if not chunk: continue
        o = chunk[0]["o"]; h = max(b["h"] for b in chunk); l = min(b["l"] for b in chunk); c = chunk[-1]["c"]
        v = sum(b.get("v",0) for b in chunk)
        out.append({"o": o, "h": h, "l": l, "c": c, "v": v})
    return out

def _ensure_sorted(bars: List[dict]) -> List[dict]:
    # If timestamps exist, sort; else assume already chronological
    if bars and "t" in bars[0]:
        return sorted(bars, key=lambda x: x["t"])
    return bars

def seed_from_broker(state: Dict[str, Any]) -> Dict[str, Any]:
    cfg = state.get("cfg", {}) or {}
    data = cfg.get("data") or {}
    minutes = int(data.get("history_seed_minutes", 60))
    broker_name = (cfg.get("broker") or {}).get("broker","paper").lower()
    symbols = state.get("symbols", [])
    tf_map = (cfg.get("bar_builder") or {}).get("timeframes") or state.get("bar_builder",{}).get("timeframes") or {"1m": 60}

    # import adapters
    if broker_name == "zerodha":
        from .brokers.zerodha import ZerodhaBroker as B
    elif broker_name == "angel":
        from .brokers.angel import AngelBroker as B
    else:
        # paper mode: just seed flat bars
        for s in symbols:
            last = state["last_price"].get(s, 100.0)
            bars_1m = [{"o": last, "h": last, "l": last, "c": last, "v": 0} for _ in range(minutes)]
            # assign to bars_tf
            for tf, sec in tf_map.items():
                state.setdefault("bars_tf", {}).setdefault(tf, {}).setdefault(s, [])
                state["bars_tf"][tf][s] = _aggregate_1m_to_tf(bars_1m, int(sec or 60))
            state["last_price"][s] = last
        state["seed_done"] = True
        return state

    b = B(cfg)
    # try fetch per symbol
    for s in symbols:
        try:
            bars_1m = b.get_1m_candles(s, minutes, cfg)
        except Exception as e:
            bars_1m = []
        bars_1m = _ensure_sorted(bars_1m)
        if not bars_1m:
            # fallback: flat
            lp = state["last_price"].get(s, 100.0)
            bars_1m = [{"o": lp, "h": lp, "l": lp, "c": lp, "v": 0} for _ in range(minutes)]
        # write into tf stores
        for tf, sec in tf_map.items():
            state.setdefault("bars_tf", {}).setdefault(tf, {}).setdefault(s, [])
            state["bars_tf"][tf][s] = _aggregate_1m_to_tf(bars_1m, int(sec or 60))
        # set last_price
        if bars_1m:
            state["last_price"][s] = float(bars_1m[-1]["c"])
    state["seed_done"] = True
    return state
