from __future__ import annotations
from typing import Dict, Any, Iterable
from random import uniform

def sim_ticks(symbols: Iterable[str], base: Dict[str, float] | None = None):
    base = base or {s: 100.0 for s in symbols}
    while True:
        for s in symbols:
            base[s] = max(1.0, base[s] + uniform(-0.25, 0.25))
            yield {"symbol": s, "ltp": base[s]}
