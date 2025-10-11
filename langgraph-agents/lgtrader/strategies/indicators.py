from __future__ import annotations
from typing import List, Optional, Tuple

def ema(series: List[float], period: int) -> Optional[float]:
    if len(series) < period: return None
    k = 2 / (period + 1); e = series[0]
    for price in series[1:]: e = price * k + e * (1 - k)
    return e

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

def macd(series: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float]]:
    if len(series) < slow + signal: return None, None
    def _ema(period: int) -> List[float]:
        k = 2 / (period + 1); out=[]; e=series[0]; out.append(e)
        for price in series[1:]: e = price * k + e * (1 - k); out.append(e)
        return out
    ema_fast = _ema(fast); ema_slow = _ema(slow)
    macd_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
    if len(macd_line) < signal: return None, None
    k = 2 / (signal + 1); s = macd_line[0]; signal_vals=[s]
    for v in macd_line[1:]: s = v * k + s * (1 - k); signal_vals.append(s)
    return macd_line[-1], signal_vals[-1]
