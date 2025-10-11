from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

def body(b): return abs(b["c"] - b["o"])
def is_bull(b): return b["c"] > b["o"]
def is_bear(b): return b["c"] < b["o"]

class MorningStar(Strategy):
    name = "morning_star"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if len(bars) < 3: return None
        a, b, c = bars[-3], bars[-2], bars[-1]
        # Basic morning star: large bear, small body (gap down optional), large bull closing into/above mid of a
        if is_bear(a) and body(a) > (a["h"]-a["l"])*0.4:
            if body(b) <= (b["h"]-b["l"])*0.25:
                # confirmation: strong bullish third bar
                if is_bull(c) and c["c"] >= a["o"] - (body(a)*0.25):
                    return {"symbol": symbol, "side": "BUY"}
        return None
