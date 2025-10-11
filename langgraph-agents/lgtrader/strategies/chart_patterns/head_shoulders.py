from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
from ..base import Strategy

def _swing_points(closes: List[float], lookback: int = 3) -> List[Tuple[int, float]]:
    pts = []
    for i in range(lookback, len(closes)-lookback):
        w = closes[i-lookback:i+lookback+1]
        if closes[i] == max(w) or closes[i] == min(w):
            pts.append((i, closes[i]))
    return pts

class HeadShoulders(Strategy):
    name = "head_shoulders"
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]:
        closes = [b["c"] for b in bars]
        if len(closes) < 50: return None
        pts = _swing_points(closes, 3)
        if len(pts) < 5: return None
        # rough pattern: L shoulder < Head > R shoulder for tops; inverse for bottoms
        # take last 7 swings for evaluation
        S = pts[-7:]
        highs = [p for p in S if p[1] >= max(closes[max(0,p[0]-2):p[0]+3])]
        lows  = [p for p in S if p[1] <= min(closes[max(0,p[0]-2):p[0]+3])]
        # detect top H&S
        if len(highs) >= 3:
            hs = sorted(highs, key=lambda x: x[0])
            L, H, R = hs[-3:]
            if H[1] > L[1] and H[1] > R[1] and abs(L[1]-R[1]) <= (H[1]*0.03):
                # neckline: min low between L and R
                i0, i1 = L[0], R[0]
                neck = min(closes[i0:i1+1])
                if closes[-1] < neck:
                    return {"symbol": symbol, "side": "SELL"}
        # detect inverse H&S
        if len(lows) >= 3:
            hs = sorted(lows, key=lambda x: x[0])
            L, H, R = hs[-3:]
            if H[1] < L[1] and H[1] < R[1] and abs(L[1]-R[1]) <= (abs(H[1])*0.03 + 1e-6):
                i0, i1 = L[0], R[0]
                neck = max(closes[i0:i1+1])
                if closes[-1] > neck:
                    return {"symbol": symbol, "side": "BUY"}
        return None
