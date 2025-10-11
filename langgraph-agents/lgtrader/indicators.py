from __future__ import annotations
from typing import List, Optional

def atr(bars: List[dict], period: int = 14) -> Optional[float]:
    """Compute ATR over the last `period` bars. Bars must have o,h,l,c keys.
    Returns ATR of the most recent bar (Wilder's smoothing approximation)."""
    if not bars or len(bars) < period + 1:
        return None
    trs = []
    for i in range(1, len(bars)):
        h = float(bars[i]["h"]); l = float(bars[i]["l"]); pc = float(bars[i-1]["c"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return None
    # Wilder's smoothing (EMA with alpha=1/period) for last value
    # here we just compute simple SMA of last `period` TRs for simplicity
    return sum(trs[-period:]) / period
