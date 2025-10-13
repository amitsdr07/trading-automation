"""
Angel One SmartAPI broker wrapper aligned with the official smartapi-python repo.

Refs:
- GitHub (official): angel-one/smartapi-python
- Docs: smartapi.angelbroking.com/docs/User
- Notes on WebSocket v2 + method variants in SDK

pip install smartapi-python pyotp
Env (required):
  SMARTAPI_API_KEY, SMARTAPI_CLIENT_ID, SMARTAPI_PIN, SMARTAPI_TOTP_SECRET
Optional:
  SMARTAPI_FEED_TOKEN
"""

from __future__ import annotations
from typing import Optional, Any, Dict, Tuple, List
import os
import json
from datetime import datetime
from dateutil import tz
from dotenv import load_dotenv

# ---------- import SmartConnect (repo-consistent) ----------
try:
    from SmartApi.smartConnect import SmartConnect  # official package path
except Exception:  # older wheels sometimes expose fallback
    from smartapi import SmartConnect  # type: ignore

import pyotp  # type: ignore


class SmartAPIBroker:
    """Angel One SmartAPI wrapper following the official repo’s method names/params."""

    def __init__(self, exchange: str, tradingsymbol: str, symboltoken: Optional[str] = None):
        self.exchange = exchange.upper()  # e.g., NSE, BSE, NFO
        self.tradingsymbol = tradingsymbol
        self.token = str(symboltoken) if symboltoken is not None else None

        # Load API key and access token
        load_dotenv()

        api_key = os.getenv("SMARTAPI_API_KEY")
        client_id = os.getenv("SMARTAPI_CLIENT_ID")
        pin = os.getenv("SMARTAPI_PIN")
        totp_secret = os.getenv("SMARTAPI_TOTP_SECRET")
        if not all([api_key, client_id, pin, totp_secret]):
            raise RuntimeError("Set SMARTAPI_API_KEY, SMARTAPI_CLIENT_ID, SMARTAPI_PIN, SMARTAPI_TOTP_SECRET")

        self.api_key = api_key
        self.client_id = client_id
        self.smart = SmartConnect(api_key)

        # login (repo-consistent)
        totp = pyotp.TOTP(totp_secret).now()
        data = self.smart.generateSession(client_id, pin, totp)
        if not data or not self._truthy(data, "status"):
            raise RuntimeError(f"SmartAPI login failed: {data}")

        # feed token (optional)
        try:
            self.feed_token = os.getenv("SMARTAPI_FEED_TOKEN") or self.smart.getfeedToken()
        except Exception:
            self.feed_token = None

    # --------------- internal response helpers (SDKs can return dict or raw JSON str) ---------------
    @staticmethod
    def _normalize(resp_raw: Any) -> Dict[str, Any]:
        if isinstance(resp_raw, dict):
            return resp_raw
        if isinstance(resp_raw, (bytes, bytearray)):
            try:
                return json.loads(resp_raw.decode("utf-8"))
            except Exception:
                return {"raw": resp_raw.decode("utf-8", "ignore")}
        if isinstance(resp_raw, str):
            try:
                return json.loads(resp_raw)
            except Exception:
                return {"raw": resp_raw.strip()}
        return {"raw": str(resp_raw)}

    @staticmethod
    def _truthy(d: Dict[str, Any], key: str) -> bool:
        v = d.get(key)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "success", "ok")
        return bool(v)

    @staticmethod
    def _extract_order_id(resp: Dict[str, Any]) -> Optional[str]:
        data = resp.get("data") or {}
        if isinstance(data, dict):
            for k in ("orderid", "order_id", "orderno", "orderNo", "uniqueorderid"):
                if k in data and data[k]:
                    return str(data[k])
        for k in ("orderid", "order_id"):
            if k in resp and resp[k]:
                return str(resp[k])
        raw = str(resp.get("raw", "")).strip()
        if raw and raw.isalnum() and 6 <= len(raw) <= 40:
            return raw
        return None

    # --------------- ORDERS (repo method names & payloads) ---------------
    def place_order(self, symbol: str, side: str, qty: int, *, product: str = "INTRADAY",
                    ordertype: str = "MARKET", price: Optional[float] = None, variety: str = "NORMAL") -> Dict[str, Any]:
        tx = "BUY" if side.lower() == "buy" else "SELL"
        order = {
            "variety": variety,                          # "NORMAL", "STOPLOSS", ...
            "tradingsymbol": self.tradingsymbol,         # e.g., "SBIN-EQ" or "RELIANCE"
            "symboltoken": self.token,                   # Angel numeric token as string
            "transactiontype": tx,                       # BUY/SELL
            "exchange": self.exchange,                   # NSE/BSE/NFO
            "ordertype": ordertype,                      # MARKET/LIMIT/SL/SLM
            "producttype": product,                      # INTRADAY/DELIVERY
            "duration": "DAY",
            "quantity": int(qty),
        }
        if ordertype.upper() == "LIMIT" and price is not None:
            order["price"] = float(price)

        order = {k: v for k, v in order.items() if v is not None}
        resp = self._normalize(self.smart.placeOrderFullResponse(order))
        if not self._truthy(resp, "status"):
            raise RuntimeError(f"[SMARTAPI ERROR] placeOrder failed: {resp}")
        oid = self._extract_order_id(resp)
        print(f"[SMARTAPI] {tx} {qty} {self.exchange}:{self.tradingsymbol} placed (order_id={oid})")
        return resp

    def modify_order(self, order_id: str, *, price: Optional[float] = None, quantity: Optional[int] = None,
                     ordertype: Optional[str] = None, variety: str = "NORMAL") -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "variety": variety,
            "orderid": order_id,
        }
        if price is not None:
            payload["price"] = float(price)
        if quantity is not None:
            payload["quantity"] = int(quantity)
        if ordertype is not None:
            payload["ordertype"] = ordertype

        resp = self._normalize(self.smart.modifyOrder(payload))
        if not self._truthy(resp, "status"):
            raise RuntimeError(f"[SMARTAPI ERROR] modifyOrder failed: {resp}")
        return resp

    def cancel_order(self, order_id: str, *, variety: str = "NORMAL") -> Dict[str, Any]:
        payload = {"variety": variety, "orderid": order_id}
        resp = self._normalize(self.smart.cancelOrder(payload))
        if not self._truthy(resp, "status"):
            raise RuntimeError(f"[SMARTAPI ERROR] cancelOrder failed: {resp}")
        return resp

    # --------------- ORDER STATUS (per-order API; higher rate limit) ---------------
    def get_order_status(self, unique_order_id: Optional[str] = None, order_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Uses the newer single-order status endpoint if exposed by your SDK build; falls back to getOrderBook().
        See forum note on per-order API and limits.
        """
        # Try new function name if present
        for fn_name in ("orderStatus", "getOrderStatus", "getorderStatus"):
            fn = getattr(self.smart, fn_name, None)
            if callable(fn):
                try:
                    payload: Dict[str, Any] = {}
                    if unique_order_id:
                        payload["uniqueorderid"] = unique_order_id
                    if order_id:
                        payload["orderid"] = order_id
                    resp = self._normalize(fn(payload))
                    if resp:
                        return resp
                except Exception:
                    pass
        # Fallback: fetch whole book and filter
        book = self._normalize(self.smart.orderBook())
        if not self._truthy(book, "status"):
            return book
        oid = order_id or unique_order_id
        if not oid:
            return book
        items = book.get("data") or []
        if isinstance(items, list):
            for o in items:
                if str(o.get("orderid") or o.get("uniqueorderid")) == str(oid):
                    return {"status": True, "data": o}
        return book

    # --------------- POSITIONS / FLATTEN ---------------
    def get_positions(self) -> Dict[str, Any]:
        return self._normalize(self.smart.position())

    def close_position(self, symbol: str) -> Optional[str]:
        """Flatten current net position in this symbol with a MARKET reverse order."""
        pos = self.get_positions()
        data = pos.get("data") or []
        qty = 0
        product = "INTRADAY"
        if isinstance(data, list):
            for p in data:
                if (
                    str(p.get("tradingsymbol")) == self.tradingsymbol
                    and str(p.get("exchange")).upper() == self.exchange
                    and int(p.get("netqty", 0)) != 0
                ):
                    qty = int(p.get("netqty", 0))
                    product = str(p.get("producttype") or "INTRADAY")
                    break
        if qty == 0:
            print("[SMARTAPI] No open position to close.")
            return None

        side = "BUY" if qty < 0 else "SELL"
        resp = self.place_order(self.tradingsymbol, "buy" if side == "BUY" else "sell", abs(qty), product=product)
        return self._extract_order_id(resp)

    # --------------- LTP ---------------
    def get_last_price(self, symbol: Optional[str] = None) -> float:
        """Fetch last traded price for the stored symbol, or a different one if provided."""
        sym = symbol or self.tradingsymbol
        try:
           data = self.smart.ltpData(self.exchange, sym, self.token)
        except Exception:
           data = self.smart.ltpData(exchange=self.exchange, tradingsymbol=sym, symboltoken=self.token)
        d = self._normalize(data)
        px = ((d.get("data") or {}).get("ltp"))
        if px is None:
           raise RuntimeError(f"LTP not available: {d}")
        return float(px)

    # --------------- HISTORICAL (IST, repo-style getCandleData) ---------------
    def fetch_intraday_ist(self, start_ist: datetime, end_ist: datetime, interval: str = "ONE_MINUTE") -> List[List[Any]]:
        """
        Calls getCandleData({'exchange','symboltoken','interval','fromdate','todate'}) using IST times.
        Returns SmartAPI 'data' array: [[ts, o, h, l, c, v], ...]
        """
        if start_ist.tzinfo is None or end_ist.tzinfo is None:
            raise ValueError("start_ist/end_ist must be timezone-aware (Asia/Kolkata).")

        fmt = "%Y-%m-%d %H:%M"
        payload = {
            "exchange": self.exchange,
            "symboltoken": self.token,
            "interval": interval,
            "fromdate": start_ist.strftime(fmt),
            "todate": end_ist.strftime(fmt),
        }
        # Preferred modern function name
        data = None
        for fn_name in ("getCandleData", "historicalData"):
            fn = getattr(self.smart, fn_name, None)
            if callable(fn):
                try:
                    data = self._normalize(fn(payload))
                    break
                except Exception:
                    continue
        if not data or not self._truthy(data, "status"):
            raise RuntimeError(f"No historical data: {data}")
        arr = data.get("data") or []
        if not arr:
            raise RuntimeError("No historical candles in the requested window.")
        return arr

    # --------------- GTT (OCO) ---------------
    def create_gtt_oco(self, side: str, qty: int, stop_price: float, target_price: float, *, product: str = "DELIVERY") -> Dict[str, Any]:
        payload = {
            "tradingsymbol": self.tradingsymbol,
            "symboltoken": self.token,
            "exchange": self.exchange,
            "transactiontype": "BUY" if side.lower() == "buy" else "SELL",
            "producttype": product,
            "quantity": int(qty),
            "price": 0,
            "triggerprice": 0,
            "timeperiod": 365,
            "type": "OCO",
            "priceband": [float(target_price), float(stop_price)],
        }
        # try both method names found across SDK versions
        for fn_name in ("gttCreateRule", "createGttRule"):
            fn = getattr(self.smart, fn_name, None)
            if callable(fn):
                resp = self._normalize(fn(payload))
                if self._truthy(resp, "status"):
                    return resp
        raise RuntimeError("GTT OCO creation failed (no working method)")

    def cancel_all_gtt_for_symbol(self) -> None:
        rules = None
        for fn_name in ("gttGetRuleList", "getGttRuleList"):
            fn = getattr(self.smart, fn_name, None)
            if callable(fn):
                try:
                    rules = self._normalize(fn())
                    break
                except Exception:
                    continue
        if not rules or not self._truthy(rules, "status"):
            return
        for r in (rules.get("data") or []):
            ts = r.get("tradingsymbol") or r.get("symbolname")
            rid = r.get("id") or r.get("rule_id")
            if ts == self.tradingsymbol and rid:
                for del_name in ("gttDeleteRule", "cancelGttRule"):
                    dfn = getattr(self.smart, del_name, None)
                    if callable(dfn):
                        try:
                            _ = dfn({"id": rid})
                            break
                        except Exception:
                            continue


__all__ = ["SmartAPIBroker"]
