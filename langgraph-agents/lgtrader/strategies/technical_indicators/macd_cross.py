from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from ..base import Strategy

def ema_series(series: List[float], period: int) -> List[float]:
    k = 2 / (period + 1); out=[]; e=series[0]; out.append(e)
    for price in series[1:]: e = price * k + e * (1 - k); out.append(e)
    return out

def macd_vals(series: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float]]:
    if len(series) < slow + signal: return None, None
    ema_fast = ema_series(series, fast); ema_slow = ema_series(series, slow)
    macd_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
    if len(macd_line) < signal: return None, None
    signal_vals = ema_series(macd_line, signal)
    return macd_line[-1], signal_vals[-1]

class MACDCross(Strategy):
    name = "macd_cross"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        m, s = macd_vals(closes, 12, 26, 9)
        mp, sp = macd_vals(closes[:-1], 12, 26, 9) if len(closes) > 1 else (None, None)
        if None in (m, s, mp, sp): return None
        prev = (mp - sp); cur = (m - s)
        if prev <= 0 < cur: return {"symbol": symbol, "side": "BUY"}
        if prev >= 0 > cur: return {"symbol": symbol, "side": "SELL"}
        return None
