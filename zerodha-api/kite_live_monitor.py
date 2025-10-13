"""
Kite WebSocket live monitor
===========================

Drop-in companion for `smartapi_live_monitor.monitor_with_smartapi_ws`,
implemented for Zerodha Kite using the official WebSocket client
(`kiteconnect.ticker.KiteTicker`).

Quick start
-----------

```
from kite_broker import KiteBroker
from kite_live_monitor import monitor_with_kite_ws

kb = KiteBroker(api_key=API_KEY, access_token=ACCESS_TOKEN)
# Resolve instrument tokens however you like
reliance = kb.get_instrument_token("NSE", "RELIANCE")
infosys  = kb.get_instrument_token("NSE", "INFY")

# Minimal monitor that prints ticks
monitor_with_kite_ws(kb, tokens=[reliance, infosys])
```

Design goals
------------
- Similar feel to a hypothetical `monitor_with_smartapi_ws`
- Accept either a `KiteBroker`, raw `KiteConnect` creds, or an existing
  `KiteTicker`
- Simple callback hooks: `on_tick`, `on_connect`, `on_close`, `on_error`
- Automatic resubscribe on reconnect
- Easy mode selection: `ltp`, `quote`, or `full`

Notes
-----
- The WebSocket requires a **fresh** `access_token` valid for the day.
- Subscription list must be *instrument tokens* (ints), not strings like
  `NSE:RELIANCE`.
- `on_tick` receives the full list of ticks as delivered by Kite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Any
import threading
import time

try:
    from kiteconnect import KiteConnect
    from kiteconnect.ticker import KiteTicker
except Exception as _e:  # pragma: no cover - surfaced at runtime
    KiteConnect = None  # type: ignore
    KiteTicker = None  # type: ignore

# Callback type aliases
OnTickCb = Callable[[List[dict]], None]
OnErrCb = Callable[[Exception], None]
OnVoidCb = Callable[[], None]


@dataclass
class WSCallbacks:
    on_tick: Optional[OnTickCb] = None
    on_connect: Optional[OnVoidCb] = None
    on_close: Optional[OnVoidCb] = None
    on_error: Optional[OnErrCb] = None
    on_reconnect: Optional[OnVoidCb] = None
    on_noreconnect: Optional[OnVoidCb] = None


MODE_MAP = {
    "ltp": "MODE_LTP",
    "quote": "MODE_QUOTE",
    "full": "MODE_FULL",
}


class KiteLiveMonitor:
    """Thin wrapper around `KiteTicker` with auto-(re)subscribe and hooks."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
        *,
        kite: Optional[KiteConnect] = None,
        ticker: Optional[KiteTicker] = None,
        tokens: Optional[Sequence[int]] = None,
        mode: str = "quote",
        callbacks: Optional[WSCallbacks] = None,
        reconnect: bool = True,
        reconnect_max_tries: int = 50,
        reconnect_max_delay: int = 60,
    ) -> None:
        if KiteConnect is None or KiteTicker is None:
            raise ImportError("kiteconnect is not installed. Run `pip install kiteconnect`.")

        if ticker is not None:
            self.ticker = ticker
            self.api_key = None
            self.access_token = None
        else:
            if kite is None:
                if not api_key or not access_token:
                    raise ValueError("Provide either (kite) or (api_key + access_token).")
                kite = KiteConnect(api_key=api_key)
                kite.set_access_token(access_token)
            # Create a fresh ticker from the client
            self.api_key = kite.api_key
            self.access_token = kite.access_token
            self.ticker = KiteTicker(self.api_key, self.access_token)

        self.tokens: List[int] = list(tokens or [])
        self.mode_key = mode.lower()
        if self.mode_key not in MODE_MAP:
            raise ValueError("mode must be one of: 'ltp', 'quote', 'full'")

        self.callbacks = callbacks or WSCallbacks()
        self.reconnect = reconnect
        self.reconnect_max_tries = reconnect_max_tries
        self.reconnect_max_delay = reconnect_max_delay
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Bind event handlers
        self.ticker.on_ticks = self._on_ticks
        self.ticker.on_connect = self._on_connect
        self.ticker.on_close = self._on_close
        self.ticker.on_error = self._on_error
        self.ticker.on_reconnect = self._on_reconnect
        self.ticker.on_noreconnect = self._on_noreconnect

    # --------------------------- public controls --------------------------- #
    def start(self, blocking: bool = True) -> None:
        """Start the WebSocket; blocks unless `blocking=False`."""
        self._running = True
        if blocking:
            self.ticker.connect(
                threaded=False,
                disable_ssl_verification=False,
                reconnect=self.reconnect,
                reconnect_max_tries=self.reconnect_max_tries,
                reconnect_max_delay=self.reconnect_max_delay,
            )
        else:
            self._thread = threading.Thread(target=self._connect_loop, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            self.ticker.close()
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def set_tokens(self, tokens: Iterable[int]) -> None:
        self.tokens = list(tokens)
        try:
            if self.tokens:
                self.ticker.subscribe(self.tokens)
                self._apply_mode(self.tokens)
        except Exception:
            # Ignore if socket isn't connected yet; on_connect will subscribe.
            pass

    # ---------------------------- internal glue --------------------------- #
    def _connect_loop(self) -> None:
        try:
            self.ticker.connect(
                threaded=False,
                disable_ssl_verification=False,
                reconnect=self.reconnect,
                reconnect_max_tries=self.reconnect_max_tries,
                reconnect_max_delay=self.reconnect_max_delay,
            )
        except Exception as e:
            self._emit_error(e)

    def _apply_mode(self, tokens: Sequence[int]) -> None:
        mode_name = MODE_MAP[self.mode_key]
        mode_val = getattr(self.ticker, mode_name)
        self.ticker.set_mode(mode_val, list(tokens))

    # ------------------------------- events -------------------------------- #
    def _on_connect(self, ws: Any, response: Any) -> None:  # noqa: ANN001
        # Subscribe & set mode on connect
        if self.tokens:
            try:
                self.ticker.subscribe(self.tokens)
                self._apply_mode(self.tokens)
            except Exception as e:
                self._emit_error(e)
        if self.callbacks.on_connect:
            try:
                self.callbacks.on_connect()
            except Exception:
                pass

    def _on_ticks(self, ws: Any, ticks: List[dict]) -> None:  # noqa: ANN001
        if self.callbacks.on_tick:
            try:
                self.callbacks.on_tick(ticks)
            except Exception:
                pass

    def _on_close(self, ws: Any, code: int, reason: str) -> None:  # noqa: ANN001
        if self.callbacks.on_close:
            try:
                self.callbacks.on_close()
            except Exception:
                pass

    def _on_reconnect(self, ws: Any, attempt_count: int) -> None:  # noqa: ANN001
        # Re-subscribe on reconnect; Kite auto-clears subs
        if self.tokens:
            try:
                self.ticker.subscribe(self.tokens)
                self._apply_mode(self.tokens)
            except Exception as e:
                self._emit_error(e)
        if self.callbacks.on_reconnect:
            try:
                self.callbacks.on_reconnect()
            except Exception:
                pass

    def _on_noreconnect(self, ws: Any) -> None:  # noqa: ANN001
        if self.callbacks.on_noreconnect:
            try:
                self.callbacks.on_noreconnect()
            except Exception:
                pass

    def _on_error(self, ws: Any, code: int, reason: Exception) -> None:  # noqa: ANN001
        self._emit_error(reason)

    def _emit_error(self, exc: Exception) -> None:
        if self.callbacks.on_error:
            try:
                self.callbacks.on_error(exc)
            except Exception:
                pass


# ------------------------- functional-style wrapper ------------------------- #

def monitor_with_kite_ws(
    client_or_api_key: Any,
    tokens: Sequence[int],
    *,
    access_token: Optional[str] = None,
    mode: str = "quote",
    on_tick: Optional[OnTickCb] = None,
    on_connect: Optional[OnVoidCb] = None,
    on_close: Optional[OnVoidCb] = None,
    on_error: Optional[OnErrCb] = None,
    on_reconnect: Optional[OnVoidCb] = None,
    on_noreconnect: Optional[OnVoidCb] = None,
    reconnect: bool = True,
    reconnect_max_tries: int = 50,
    reconnect_max_delay: int = 60,
    blocking: bool = True,
) -> KiteLiveMonitor:
    """Start a WebSocket monitor with a simple one-liner API.

    Parameters
    ----------
    client_or_api_key : KiteBroker | KiteConnect | KiteTicker | str
        - If a string, treated as `api_key` (requires `access_token`)
        - If a `KiteBroker` or `KiteConnect`, the access token is read from it
        - If a `KiteTicker`, it will be used directly
    tokens : Sequence[int]
        Instrument tokens to subscribe to.
    mode : "ltp" | "quote" | "full"
        Subscription depth/mode.
    blocking : bool
        If True (default) this call will block until the socket is closed.
        Set to False to run in a background thread; keep a reference to
        the returned `KiteLiveMonitor` and call `.stop()` when done.
    """
    # Lazy imports/typing to avoid strict dependency on kite_broker
    KiteBroker = None  # type: ignore
    try:
        from kite_broker import KiteBroker as _KB  # noqa: WPS433
        KiteBroker = _KB  # type: ignore
    except Exception:
        pass

    callbacks = WSCallbacks(
        on_tick=on_tick,
        on_connect=on_connect,
        on_close=on_close,
        on_error=on_error,
        on_reconnect=on_reconnect,
        on_noreconnect=on_noreconnect,
    )

    # Normalize inputs
    kb = None
    kite = None
    ticker = None

    if KiteBroker is not None and isinstance(client_or_api_key, KiteBroker):
        kb = client_or_api_key
        kite = kb.kite
    elif KiteConnect is not None and isinstance(client_or_api_key, KiteConnect):
        kite = client_or_api_key
    elif KiteTicker is not None and isinstance(client_or_api_key, KiteTicker):
        ticker = client_or_api_key
    elif isinstance(client_or_api_key, str):
        api_key = client_or_api_key
        if not access_token:
            raise ValueError("When passing api_key as str, you must also pass access_token")
        monitor = KiteLiveMonitor(
            api_key=api_key,
            access_token=access_token,
            tokens=tokens,
            mode=mode,
            callbacks=callbacks,
            reconnect=reconnect,
            reconnect_max_tries=reconnect_max_tries,
            reconnect_max_delay=reconnect_max_delay,
        )
        monitor.start(blocking=blocking)
        return monitor
    else:
        raise TypeError(
            "client_or_api_key must be KiteBroker, KiteConnect, KiteTicker, or api_key string"
        )

    monitor = KiteLiveMonitor(
        kite=kite,
        ticker=ticker,
        tokens=tokens,
        mode=mode,
        callbacks=callbacks,
        reconnect=reconnect,
        reconnect_max_tries=reconnect_max_tries,
        reconnect_max_delay=reconnect_max_delay,
    )
    monitor.start(blocking=blocking)
    return monitor
