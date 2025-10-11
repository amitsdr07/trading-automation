from __future__ import annotations
from typing import Optional, Dict, Any
from .indicators import rsi

class RSICross:
    name = "rsi_cross"
    def __init__(self, low: float = 30.0, high: float = 70.0): self.low=low; self.high=high

    def on_price(self, closes: list[float], symbol: str) -> Optional[Dict[str, Any]]:
        val = rsi(closes, 14)
        if val is None: return None
        if len(closes) < 2: return None
        prev = rsi(closes[:-1], 14) or val
        if prev < self.low <= val: return {"symbol": symbol, "side": "BUY"}
        if prev > self.high >= val: return {"symbol": symbol, "side": "SELL"}
        return None
