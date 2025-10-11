from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

def _is_bullish(b): return b["c"] > b["o"]
def _is_bearish(b): return b["c"] < b["o"]

class Engulfing(Strategy):
    name = "engulfing"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if len(bars) < 2: return None
        a, b = bars[-2], bars[-1]
        # bullish engulfing: current bull wraps previous bear body
        if _is_bullish(b) and _is_bearish(a) and b["o"] <= a["c"] and b["c"] >= a["o"]:
            return {"symbol": symbol, "side": "BUY"}
        # bearish engulfing
        if _is_bearish(b) and _is_bullish(a) and b["o"] >= a["c"] and b["c"] <= a["o"]:
            return {"symbol": symbol, "side": "SELL"}
        return None
