"""
KiteBroker — a thin wrapper around the official Kite Connect client
=================================================================

This module provides a KiteBroker class with a similar feel to a
SmartAPIBroker-style helper. It centralizes:

- Client initialization (using an access token or by exchanging a
  one-time `request_token` for an access token)
- Optional persistence of the access token to a file
- Convenience helpers for instruments, instrument token lookup,
  quotes/LTP, historical bars, and basic order flows

It also exposes `get_kite_instrument_token` and `fetch_intraday_kite`
helpers to match the usage pattern in your snippet.

Requirements
------------
- `kiteconnect` Python package (official Zerodha SDK)

    pip install kiteconnect

Notes
-----
- Zerodha authentication is interactive. In production you typically
  keep and reuse a valid `access_token` for the trading day. This
  wrapper lets you load/save that token.
- Historical data API is available only for certain plans; handle
  `kiteconnect.exceptions.InputException` accordingly.
- Timezones: Kite’s `historical_data` accepts naive datetimes in local
  time OR timezone-aware datetimes. In this wrapper we accept tz-aware
  datetimes; if naive, we assume they are in UTC and convert to India
  Standard Time (IST) where appropriate. Adjust to your app’s policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
import json
import os
from dotenv import load_dotenv

try:
    from kiteconnect import KiteConnect
    from kiteconnect.exceptions import KiteException
except Exception as _e:  # pragma: no cover - import error surfaced at runtime
    KiteConnect = None  # type: ignore
    KiteException = Exception  # type: ignore


EXCHANGE_MAP = {
    # Canonicalize a few common aliases -> Kite exchange codes
    "NSE": "NSE",
    "BSE": "BSE",
    "NFO": "NFO",
    "CDS": "CDS",
    "MCX": "MCX",
}


@dataclass
class KiteCredentials:
    api_key: str
    api_secret: Optional[str] = None
    access_token: Optional[str] = None


class KiteBroker:
    """Convenience wrapper for the official Kite Connect client.

    Examples
    --------
    Basic init if you *already* have today's access token (recommended):

    >>> kb = KiteBroker(exchange="NSE", symbol="RELIANCE", api_key=os.getenv("KITE_API_KEY"), access_token=os.getenv("KITE_ACCESS_TOKEN"))

    First-time init with request token -> exchange for access token:

    >>> kb = KiteBroker(api_key=os.getenv("KITE_API_KEY"))
    >>> kb.login_with_request_token(request_token, api_secret=os.getenv("KITE_API_SECRET"))

    Looking up instrument token & fetching minute bars:

    >>> token = kb.get_instrument_token("NSE", "RELIANCE")
    >>> bars = kb.fetch_historical(token, start_utc, end_utc, interval="minute")
    """

    def __init__(
        self,
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        token_store_path: Optional[str] = None,
    ) -> None:
        if KiteConnect is None:
            raise ImportError(
                "kiteconnect is not installed. Run `pip install kiteconnect`."
            )

        self.exchange = EXCHANGE_MAP.get((exchange or "").upper(), exchange)
        self.symbol = symbol

        # Load API key and access token
        load_dotenv()

        API_KEY = os.getenv("KITE_API_KEY")
        with open(".kite_access_token") as f:
             ACCESS_TOKEN = f.read().strip()

        kite = KiteConnect(api_key=API_KEY)
        kite.set_access_token(ACCESS_TOKEN)

        # Resolve credentials from args -> env -> file

        self.api_key = api_key or os.getenv("KITE_API_KEY")
        print(self.api_key)
        if not self.api_key:
            raise ValueError("api_key is required (arg or env KITE_API_KEY)")

        self.kite = KiteConnect(api_key=self.api_key)

        # Access token handling
        self.token_store_path = token_store_path or os.getenv(
            "KITE_TOKEN_PATH", os.path.expanduser(".kite_access_token")
        )

        access_token = (
            access_token
            or os.getenv("KITE_ACCESS_TOKEN")
            or self._load_access_token_from_file()
        )
        print(access_token)
        if access_token:
            self.set_access_token(access_token)

    # ---------------------------- Auth helpers ---------------------------- #
    def login_with_request_token(self, request_token: str, api_secret: Optional[str] = None) -> str:
        """Exchange a `request_token` for an access token and set it.

        Returns the access token and persists it if `token_store_path` is set.
        """
        if not request_token:
            raise ValueError("request_token must be provided")
        api_secret = api_secret or os.getenv("KITE_API_SECRET")
        if not api_secret:
            raise ValueError("api_secret is required (arg or env KITE_API_SECRET)")

        data = self.kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        self.set_access_token(access_token)
        self._save_access_token_to_file(access_token)
        return access_token

    def set_access_token(self, access_token: str) -> None:
        self.kite.set_access_token(access_token)

    # ---------------------------- Instruments ---------------------------- #
    def instruments(self, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return list of instruments for an exchange (or all if None)."""
        ex = EXCHANGE_MAP.get((exchange or "").upper(), exchange)
        return self.kite.instruments(ex)

    def get_instrument_token(self, exchange: str, tradingsymbol: str) -> Optional[int]:
        """Find the numeric instrument token for an exchange + tradingsymbol.

        Returns None if not found.
        """
        ex = EXCHANGE_MAP.get((exchange or "").upper(), exchange)
        instruments = self.kite.instruments(ex)
        for inst in instruments:
            if str(inst.get("tradingsymbol", "")).upper() == tradingsymbol.upper():
                return inst.get("instrument_token")
        return None

    # ----------------------------- Market data ---------------------------- #
    def quote(self, *instrument_tokens: int) -> Dict[str, Any]:
        """Fetch quote for one or more numeric instrument tokens."""
        tradings = [f"NSE:{self.symbol}"] if (self.symbol and not instrument_tokens) else []
        query: Iterable[str | int] = instrument_tokens or tradings
        return self.kite.quote(list(query))

    def ltp(self, *instrument_tokens: int) -> Dict[str, Any]:
        return self.kite.ltp(list(instrument_tokens))

    def fetch_historical(
        self,
        instrument_token: int,
        start_dt: datetime,
        end_dt: datetime,
        interval: str = "minute",
        continuous: bool = False,
        oi: bool = False,
    ) -> List[Dict[str, Any]]:
        """Fetch historical bars.

        Parameters
        ----------
        instrument_token : int
            Numeric instrument token.
        start_dt, end_dt : datetime
            Accepts tz-aware UTC datetimes; naive datetimes are assumed UTC.
        interval : str
            One of: "minute", "3minute", "5minute", "10minute", "15minute",
            "30minute", "60minute", "day" (as supported by Kite).
        continuous : bool
        oi : bool

        Returns
        -------
        List of bar dicts with keys like date, open, high, low, close, volume, oi.
        """
        # Kite expects ISO8601; accepts tz-aware. Normalize naive to UTC.
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=None)  # treat as UTC naive
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=None)
        return self.kite.historical_data(
            instrument_token, start_dt, end_dt, interval, continuous=continuous, oi=oi
        )

    # ------------------------------- Orders ------------------------------ #
    def place_order(
        self,
        tradingsymbol: str,
        exchange: str = "NSE",
        transaction_type: str = "BUY",
        quantity: int = 1,
        order_type: str = "MARKET",
        product: str = "MIS",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        validity: str = "DAY",
        variety: str = "regular",
        **kwargs: Any,
    ) -> str:
        """Place an order and return the order_id."""
        ex = EXCHANGE_MAP.get(exchange.upper(), exchange)
        payload = {
            "tradingsymbol": tradingsymbol,
            "exchange": ex,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "order_type": order_type,
            "product": product,
            "validity": validity,
            **({"price": price} if price is not None else {}),
            **(
                {"trigger_price": trigger_price} if trigger_price is not None else {}
            ),
            **kwargs,
        }
        return self.kite.place_order(variety=variety, **payload)["order_id"]

    def modify_order(self, order_id: str, variety: str = "regular", **kwargs: Any) -> str:
        return self.kite.modify_order(variety=variety, order_id=order_id, **kwargs)[
            "order_id"
        ]

    def cancel_order(self, order_id: str, variety: str = "regular") -> str:
        return self.kite.cancel_order(variety=variety, order_id=order_id)["order_id"]

    # --------------------------- Token persistence ----------------------- #
    def _load_access_token_from_file(self) -> Optional[str]:
        try:
            if os.path.exists(self.token_store_path):
                with open(self.token_store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("access_token")
        except Exception:
            pass
        return None

    def _save_access_token_to_file(self, access_token: str) -> None:
        try:
            os.makedirs(os.path.dirname(self.token_store_path), exist_ok=True)
            with open(self.token_store_path, "w", encoding="utf-8") as f:
                json.dump({"access_token": access_token}, f)
        except Exception:
            # Best-effort persistence; don't crash the app.
            pass


# ----------------------------- Helper functions ----------------------------- #

def get_kite_instrument_token(kite: Any, exchange: str, tradingsymbol: str) -> Optional[int]:
    """Standalone helper to match your existing call site.

    Parameters are identical to `KiteBroker.get_instrument_token` but accept a
    raw `kite` client to preserve your current usage pattern.
    """
    ex = EXCHANGE_MAP.get(exchange.upper(), exchange)
    instruments = kite.instruments(ex)
    for inst in instruments:
        if str(inst.get("tradingsymbol", "")).upper() == tradingsymbol.upper():
            return inst.get("instrument_token")
    return None


def fetch_intraday_kite(
    kite: Any,
    instrument_token: int,
    d0_utc: datetime,
    d1_utc: datetime,
    interval: str = "minute",
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Fetch intraday bars via the raw `kite` client (to match your snippet).

    If you migrate your code to use the class method instead, call
    `KiteBroker.fetch_historical(...)`.
    """
    return kite.historical_data(
        instrument_token,
        d0_utc,
        d1_utc,
        interval,
        continuous=kwargs.get("continuous", False),
        oi=kwargs.get("oi", False),
    )
