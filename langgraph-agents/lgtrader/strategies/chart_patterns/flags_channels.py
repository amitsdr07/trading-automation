from __future__ import annotations
from typing import Optional, Dict, Any, List
from statistics import pstdev, mean
from ..base import Strategy

def slope(xs: List[float]) -> float:
    if len(xs) < 2: return 0.0
    return (xs[-1] - xs[0]) / max(1, len(xs)-1)

class FlagsChannels(Strategy):
    name = "flags_channels"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if len(bars) < 40: return None
        closes = [b["c"] for b in bars]
        prev = closes[-30:-10]  # prior impulse
        cons = closes[-10:]     # consolidation
        if len(prev) < 5: return None
        impulse = abs(slope(prev)) > (pstdev(prev) * 0.5)  # rough impulse check
        tight = (max(cons)-min(cons)) < (max(prev)-min(prev)) * 0.5
        flat  = abs(slope(cons)) < (pstdev(cons) * 0.2 + 1e-6)
        if impulse and tight and flat:
            top = max(cons); bot = min(cons); last = closes[-1]
            if last > top: return {"symbol": symbol, "side": "BUY"}   # flag up break
            if last < bot: return {"symbol": symbol, "side": "SELL"}  # flag down break
        return None
