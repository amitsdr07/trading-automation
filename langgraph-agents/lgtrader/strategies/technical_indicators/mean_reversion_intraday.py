from __future__ import annotations
from typing import Optional, Dict, Any, List
from math import sqrt
from ..base import Strategy

def sma(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def std(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n: return None
    m = sma(vals, n)
    var = sum((x-m)**2 for x in vals[-n:]) / n
    return sqrt(var)

class MeanReversionIntraday(Strategy):
    name = "mean_reversion_intraday"
    def __init__(self, n:int=20, k:float=2.0):
        self.n=n; self.k=k
    def set_params(self, params: dict):
        try:
            bb = (params or {}).get('bb') or {}
            n = int(bb.get('n', self.n))
            k = float(bb.get('k', self.k))
            self.n, self.k = n, k
        except Exception:
            pass
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        if len(closes) < self.n: return None
        m = sma(closes, self.n); s = std(closes, self.n)
        if m is None or s is None: return None
        upper = m + self.k*s; lower = m - self.k*s
        last = closes[-1]
        # contrarian: fade extremes
        if last < lower: return {"symbol": symbol, "side": "BUY"}
        if last > upper: return {"symbol": symbol, "side": "SELL"}
        return None
