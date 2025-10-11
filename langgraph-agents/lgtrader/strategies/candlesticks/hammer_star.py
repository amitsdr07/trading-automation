from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

def body(b): return abs(b["c"] - b["o"])
def upper_wick(b): return b["h"] - max(b["o"], b["c"])
def lower_wick(b): return min(b["o"], b["c"]) - b["l"]

class HammerStar(Strategy):
    name = "hammer_star"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if not bars: return None
        b = bars[-1]
        if body(b) == 0: return None
        if lower_wick(b) >= 2 * body(b) and upper_wick(b) <= body(b) * 0.5:
            return {"symbol": symbol, "side": "BUY"}      # hammer
        if upper_wick(b) >= 2 * body(b) and lower_wick(b) <= body(b) * 0.5:
            return {"symbol": symbol, "side": "SELL"}     # shooting star
        return None
