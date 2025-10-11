from __future__ import annotations
from typing import Dict, Any

class Broker:
    def __init__(self, cfg: dict): self.cfg = cfg
    def test(self) -> Dict[str, Any]: return {"ok": True}
    def place_market(self, order: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "stubbed", "order": order}
    def get_1m_candles(self, symbol: str, minutes: int, cfg: dict) -> list:
        return []

def make_broker(cfg: dict):
    name = (cfg.get("broker", {}) or {}).get("broker", "paper").lower()
    if name == "zerodha":
        from .zerodha import ZerodhaBroker
        return ZerodhaBroker(cfg)
    if name == "angel":
        from .angel import AngelBroker
        return AngelBroker(cfg)
    from .paper import PaperBroker
    return PaperBroker(cfg)
