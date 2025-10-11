from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime, timedelta
from ..utils import IST

class ZerodhaBroker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._kite = None
        try:
            from kiteconnect import KiteConnect  # noqa: F401
            self._has = True
        except Exception:
            self._has = False

    # ---------- Session ----------
    def _kite(self):
        if not self._has:
            raise RuntimeError("kiteconnect not installed")
        from kiteconnect import KiteConnect
        api_key = (self.cfg.get("broker") or {}).get("api_key")
        access_token = (self.cfg.get("broker") or {}).get("access_token")
        if not (api_key and access_token):
            raise RuntimeError("Missing api_key/access_token for Zerodha")
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        return kite

    def test(self) -> Dict[str, Any]:
        try:
            _ = self._kite()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- Orders ----------
    def place_market(self, order: Dict[str, Any]) -> Dict[str, Any]:
        # Guard with live_trading flag
        if not (self.cfg.get("broker") or {}).get("live_trading", False):
            return {"mode": "zerodha", "status": "paper_blocked", "order": order}
        kite = self._kite()
        symbol = order["symbol"]; side = order["side"]; qty = int(order["qty"])
        cmap = ((self.cfg.get("contracts") or {}).get("zerodha") or {}).get(symbol, {})
        exchange = cmap.get("exchange", "NSE")
        tsymbol  = cmap.get("tradingsymbol", symbol)
        product  = cmap.get("product", "MIS")
        variety = "regular"; order_type = "MARKET"
        trans = "BUY" if side.upper() == "BUY" else "SELL"
        try:
            res = kite.place_order(variety=variety, exchange=exchange, tradingsymbol=tsymbol, transaction_type=trans,
                                   quantity=qty, product=product, order_type=order_type)
            return {"status": "accepted", "broker_order_id": res, "raw": res}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ---------- History ----------
    def get_1m_candles(self, symbol: str, minutes: int, cfg: dict) -> List[dict]:
        # Requires instrument token from config.instruments.zerodha
        tokens = (cfg.get("instruments") or {}).get("zerodha") or {}
        token = tokens.get(symbol)
        if token is None:
            return []
        kite = self._kite()
        end = datetime.now(tz=IST)
        start = end - timedelta(minutes=minutes+2)
        try:
            data = kite.historical_data(int(token), start, end, interval="minute")
            bars = []
            for d in data:
                bars.append({"o": float(d["open"]), "h": float(d["high"]), "l": float(d["low"]), "c": float(d["close"]), "v": float(d.get("volume", 0)), "t": d.get("date")})
            return bars
        except Exception:
            return []

    def list_orders(self) -> list:
        try:
            kite = self._kite()
            return kite.orders() or []
        except Exception:
            return []
