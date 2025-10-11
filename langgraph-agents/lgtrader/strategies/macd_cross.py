from __future__ import annotations
from typing import Optional, Dict, Any
from .indicators import macd

class MACDCross:
    name = "macd_cross"
    def __init__(self): pass

    def on_price(self, closes: list[float], symbol: str) -> Optional[Dict[str, Any]]:
        m, s = macd(closes, 12, 26, 9)
        if m is None or s is None: return None
        if len(closes) < 2: return None
        m_prev, s_prev = macd(closes[:-1], 12, 26, 9)
        if m_prev is None or s_prev is None: return None
        prev = m_prev - s_prev; cur = m - s
        if prev <= 0 < cur: return {"symbol": symbol, "side": "BUY"}
        if prev >= 0 > cur: return {"symbol": symbol, "side": "SELL"}
        return None
