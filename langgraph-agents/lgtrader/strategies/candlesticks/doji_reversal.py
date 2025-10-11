from __future__ import annotations
from typing import Optional, Dict, Any, List, DefaultDict
from collections import defaultdict
from ..base import Strategy

def rng(b): return max(1e-6, b["h"] - b["l"])
def body(b): return abs(b["c"] - b["o"])

class DojiReversal(Strategy):
    name = "doji_reversal"
    def __init__(self, body_ratio: float = 0.1):
        self.last_doji = defaultdict(lambda: None)  # symbol -> (hi, lo)
        self.body_ratio = body_ratio

    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if not bars: return None
        b = bars[-1]
        # detect doji
        if body(b) <= rng(b) * self.body_ratio:
            self.last_doji[symbol] = (b["h"], b["l"])
            return None
        # if doji stored, trade on breakout
        if self.last_doji[symbol]:
            hi, lo = self.last_doji[symbol]
            if b["c"] > hi:
                self.last_doji[symbol] = None
                return {"symbol": symbol, "side": "BUY"}
            if b["c"] < lo:
                self.last_doji[symbol] = None
                return {"symbol": symbol, "side": "SELL"}
        return None
