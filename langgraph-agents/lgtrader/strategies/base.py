from __future__ import annotations
from typing import Protocol, Dict, Any, Optional, List

class Strategy(Protocol):
    name: str
    def on_bar(self, bars: List[Dict[str, float]], symbol: str) -> Optional[Dict[str, Any]]: ...
