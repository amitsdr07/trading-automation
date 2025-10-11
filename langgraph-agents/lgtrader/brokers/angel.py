from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime, timedelta
from ..utils import IST

class AngelBroker:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        try:
            from smartapi import SmartConnect  # noqa: F401
            self._has = True
        except Exception:
            self._has = False
        self._sc = None

    # ---------- Session ----------
    def _client(self):
        if not self._has:
            raise RuntimeError("smartapi not installed")
        from smartapi import SmartConnect
        broker = (self.cfg.get("broker") or {})
        api_key = broker.get("api_key")
        access_token = broker.get("access_token")
        client_id = broker.get("client_id") or broker.get("user_id") or broker.get("userid")
        if not (api_key and access_token and client_id):
            raise RuntimeError("Missing api_key/access_token/client_id for Angel")
        sc = SmartConnect(api_key)
        sc.setAccessToken(access_token)
        # Note: feed_token should be set separately for WS
        return sc

    def test(self) -> Dict[str, Any]:
        try:
            _ = self._client()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ---------- Orders ----------
    def place_market(self, order: Dict[str, Any]) -> Dict[str, Any]:
        if not (self.cfg.get("broker") or {}).get("live_trading", False):
            return {"mode": "angel", "status": "paper_blocked", "order": order}
        sc = self._client()
        symbol = order["symbol"]; side = order["side"]; qty = int(order["qty"])
        # Angel requires exchange, trading symbol token etc. We'll map via config.instruments.angel token
        cmap = ((self.cfg.get("contracts") or {}).get("angel") or {}).get(symbol, {})
        tokens = (self.cfg.get("instruments") or {}).get("angel") or {}
        token = cmap.get("symboltoken") or tokens.get(symbol)
        if token is None:
            return {"status": "error", "error": f"missing symbol token for {symbol}"}
        payload = {
            "variety": cmap.get("variety", "NORMAL"),
            "tradingsymbol": cmap.get("tradingsymbol", symbol),
            "symboltoken": str(token),
            "transactiontype": "BUY" if side.upper()=="BUY" else "SELL",
            "exchange": cmap.get("exchange", "NSE"),
            "ordertype": cmap.get("ordertype", "MARKET"),
            "producttype": cmap.get("producttype", "INTRADAY"),
            "duration": cmap.get("duration", "DAY"),
            "quantity": qty,
        }
        try:
            res = sc.placeOrder(payload)
            return {"status": "accepted", "broker_order_id": res.get("data"), "raw": res}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ---------- History ----------
    def get_1m_candles(self, symbol: str, minutes: int, cfg: dict) -> List[dict]:
        tokens = (cfg.get("instruments") or {}).get("angel") or {}
        token = tokens.get(symbol)
        if token is None:
            return []
        try:
            from smartapi import SmartConnect
        except Exception:
            return []
        sc = self._client()
        end = datetime.now(tz=IST)
        start = end - timedelta(minutes=minutes+2)
        # Angel getCandleData params (v1/v2 differ; here's common shape)
        params = {
            "exchange": "NSE",
            "symboltoken": str(token),
            "interval": "ONE_MINUTE",
            "fromdate": start.strftime("%Y-%m-%d %H:%M"),
            "todate": end.strftime("%Y-%m-%d %H:%M"),
        }
        try:
            data = sc.getCandleData(params)
            # Angel returns list of [time, open, high, low, close, volume]
            candles = data.get("data") or []
            bars = []
            for c in candles:
                if isinstance(c, (list, tuple)) and len(c) >= 6:
                    bars.append({"o": float(c[1]), "h": float(c[2]), "l": float(c[3]), "c": float(c[4]), "v": float(c[5])})
            return bars
        except Exception:
            return []

    def list_orders(self) -> list:
        try:
            sc = self._client()
            ob = sc.getOrderBook()
            return (ob.get("data") or []) if isinstance(ob, dict) else ob
        except Exception:
            return []
