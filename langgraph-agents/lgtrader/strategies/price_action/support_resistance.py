from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from ..base import Strategy

def pivot_levels(closes: List[float], lookback: int = 20, pivots: int = 3) -> Tuple[float, float]:
    # compute recent support (local minima avg) and resistance (local maxima avg)
    highs=[]; lows=[]
    for i in range(2, len(closes)-2):
        w = closes[i-2:i+3]
        if closes[i] == max(w): highs.append(closes[i])
        if closes[i] == min(w): lows.append(closes[i])
    highs = highs[-pivots:]; lows = lows[-pivots:]
    res = sum(highs)/len(highs) if highs else None
    sup = sum(lows)/len(lows) if lows else None
    return sup, res

class SupportResistance(Strategy):
    name = "support_resistance"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        if len(closes) < 25: return None
        sup, res = pivot_levels(closes, lookback=20, pivots=3)
        last = closes[-1]
        prev = closes[-2]
        if res and prev <= res < last:
            return {"symbol": symbol, "side": "BUY"}   # resistance breakout
        if sup and prev >= sup > last:
            return {"symbol": symbol, "side": "SELL"}  # support breakdown
        return None
