from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

class DoubleTopBottom(Strategy):
    name = "double_top_bottom"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        if len(bars) < 20: return None
        closes = [b["c"] for b in bars]
        # very rough: last 10 bars, seek two highs/lows near-equal within tolerance
        window = closes[-10:]
        hi = max(window); lo = min(window)
        tol = (hi - lo) * 0.02  # 2% tolerance
        # double top: two highs near hi with a dip between
        highs = [i for i,v in enumerate(window) if abs(v - hi) <= tol]
        lows = [i for i,v in enumerate(window) if abs(v - lo) <= tol]
        if len(highs) >= 2 and min(highs) < max(highs) - 1:
            # confirm break of interim low
            midlow = min(window[min(highs):max(highs)+1])
            if window[-1] < midlow: return {"symbol": symbol, "side": "SELL"}
        if len(lows) >= 2 and min(lows) < max(lows) - 1:
            midhigh = max(window[min(lows):max(lows)+1])
            if window[-1] > midhigh: return {"symbol": symbol, "side": "BUY"}
        return None
