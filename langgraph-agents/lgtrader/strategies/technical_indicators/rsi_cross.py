from __future__ import annotations
from typing import Optional, Dict, Any, List
from ..base import Strategy

def rsi(series: List[float], period: int = 14) -> Optional[float]:
    n = len(series)
    if n <= period: return None
    gains = 0.0; losses = 0.0
    for i in range(1, period + 1):
        diff = series[i] - series[i-1]
        if diff >= 0: gains += diff
        else: losses -= diff
    avg_gain = gains / period; avg_loss = losses / period
    for i in range(period + 1, n):
        diff = series[i] - series[i-1]
        gain = max(diff, 0.0); loss = max(-diff, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss; return 100 - (100 / (1 + rs))

class RSICross(Strategy):
    name = "rsi_cross"
    def __init__(self, low: float = 30.0, high: float = 70.0): self.low=low; self.high=high
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        val = rsi(closes, 14); prev = rsi(closes[:-1], 14) if len(closes) > 1 else None
        if val is None or prev is None: return None
        if prev < self.low <= val: return {"symbol": symbol, "side": "BUY"}
        if prev > self.high >= val: return {"symbol": symbol, "side": "SELL"}
        return None
