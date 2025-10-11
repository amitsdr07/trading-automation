from __future__ import annotations
from typing import Optional, Dict, Any, List, DefaultDict
from collections import defaultdict
from datetime import time as dtime
from ..base import Strategy

class OpeningRangeBreakout(Strategy):
    name = "opening_range_breakout"
    def __init__(self, minutes: int = 15):
        self.minutes = minutes
        self.range_hi = defaultdict(lambda: None)
        self.range_lo = defaultdict(lambda: None)
        self.frozen = defaultdict(lambda: False)

    def _in_range_window(self, bars: List[Dict[str, float]]) -> bool:
        # bars don't carry timestamps; rely on count as approximation.
        return len(bars) <= max(1, int(self.minutes))

    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if not bars: return None
        if self._in_range_window(bars):
            h = max([b["h"] for b in bars])
            l = min([b["l"] for b in bars])
            self.range_hi[symbol] = h; self.range_lo[symbol] = l
            return None
        if self.frozen[symbol]: return None
        last = bars[-1]["c"]
        if self.range_hi[symbol] and last > self.range_hi[symbol]:
            self.frozen[symbol] = True
            return {"symbol": symbol, "side": "BUY"}
        if self.range_lo[symbol] and last < self.range_lo[symbol]:
            self.frozen[symbol] = True
            return {"symbol": symbol, "side": "SELL"}
        return None
