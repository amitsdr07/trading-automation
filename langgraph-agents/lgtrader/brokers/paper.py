from __future__ import annotations
from typing import Dict, Any

class PaperBroker:
    def __init__(self, cfg: dict): self.cfg = cfg
    def test(self) -> Dict[str, Any]: return {"ok": True, "mode": "paper"}
    def place_market(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return {"mode":"paper","status":"accepted","order": order}
