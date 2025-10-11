from __future__ import annotations
from typing import Optional, Dict, Any
from .indicators import ema

class EMA915:
    name = "ema_9_15"
    def __init__(self): pass

    def on_price(self, closes: list[float], symbol: str) -> Optional[Dict[str, Any]]:
        e9 = ema(closes, 9); e15 = ema(closes, 15)
        if e9 is None or e15 is None: return None
        if len(closes) < 2: return None
        e9_prev = ema(closes[:-1], 9); e15_prev = ema(closes[:-1], 15)
        if e9_prev is None or e15_prev is None: return None
        crossed_up = e9_prev <= e15_prev and e9 > e15
        crossed_dn = e9_prev >= e15_prev and e9 < e15
        if crossed_up: return {"symbol": symbol, "side": "BUY"}
        if crossed_dn: return {"symbol": symbol, "side": "SELL"}
        return None
