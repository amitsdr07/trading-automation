from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

def ema(series: List[float], period: int) -> Optional[float]:
    if len(series) < period: return None
    k = 2 / (period + 1); e = series[0]
    for price in series[1:]: e = price * k + e * (1 - k)
    return e

class EMA915(Strategy):
    name = "ema_9_15"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        e9 = ema(closes, 9); e15 = ema(closes, 15)
        if e9 is None or e15 is None or len(closes) < 2: return None
        e9_prev = ema(closes[:-1], 9); e15_prev = ema(closes[:-1], 15)
        if e9_prev is None or e15_prev is None: return None
        crossed_up = e9_prev <= e15_prev and e9 > e15
        crossed_dn = e9_prev >= e15_prev and e9 < e15
        if crossed_up: return {"symbol": symbol, "side": "BUY"}
        if crossed_dn: return {"symbol": symbol, "side": "SELL"}
        return None
