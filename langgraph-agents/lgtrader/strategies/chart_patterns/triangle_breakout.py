from __future__ import annotations
from typing import Optional, Dict, Any, List
from statistics import mean
from ..base import Strategy

def local_extrema(closes: List[float], lookback: int = 5):
    highs=[]; lows=[]
    for i in range(lookback, len(closes)-lookback):
        w = closes[i-lookback:i+lookback+1]
        if closes[i] == max(w): highs.append((i, closes[i]))
        if closes[i] == min(w): lows.append((i, closes[i]))
    return highs, lows

class TriangleBreakout(Strategy):
    name = "triangle_breakout"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if len(bars) < 40: return None
        closes = [b["c"] for b in bars]
        highs, lows = local_extrema(closes, lookback=3)
        if len(highs) < 3 or len(lows) < 3: return None
        # approximate slopes: last two highs and lows
        h_slope = (highs[-1][1] - highs[-2][1]) / max(1, highs[-1][0]-highs[-2][0])
        l_slope = (lows[-1][1] - lows[-2][1]) / max(1, lows[-1][0]-lows[-2][0])
        last = closes[-1]
        # contracting if h_slope<0 and l_slope>0
        if h_slope < 0 and l_slope > 0:
            top = max([p for _,p in highs[-3:]]); bottom = min([p for _,p in lows[-3:]])
            if last > top: return {"symbol": symbol, "side": "BUY"}
            if last < bottom: return {"symbol": symbol, "side": "SELL"}
        return None
