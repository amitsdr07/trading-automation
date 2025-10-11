from __future__ import annotations
from typing import Callable, Dict, Any, Iterable, List, Optional
from .utils import now_ist

# =========================
# Zerodha KiteTicker Runner
# =========================
class ZerodhaWSRunner:
    def __init__(self, cfg: dict, symbols: Iterable[str], tokens_map: Dict[str, Any], on_tick: Callable[[Dict[str, Any]], None]):
        self.cfg = cfg
        self.symbols = list(symbols)
        self.tokens_map = tokens_map or {}
        self.on_tick_cb = on_tick
        self.connected = False
        self._kws = None

    def _resolve_tokens(self) -> List[int]:
        toks = []
        for s in self.symbols:
            tok = self.tokens_map.get(s)
            if tok is None:
                continue
            try:
                toks.append(int(tok))
            except Exception:
                pass
        return toks

    def start(self):
        try:
            from kiteconnect import KiteTicker
        except Exception as e:
            self.on_tick_cb({"error": f"kiteconnect_ticker_not_installed: {e}"})
            return

        api_key = (self.cfg.get("broker") or {}).get("api_key")
        access_token = (self.cfg.get("broker") or {}).get("access_token")
        if not api_key or not access_token:
            self.on_tick_cb({"error": "missing_zerodha_api_key_or_access_token"})
            return

        tokens = self._resolve_tokens()
        if not tokens:
            self.on_tick_cb({"error": "no_tokens_to_subscribe"})
            return

        kws = KiteTicker(api_key, access_token)
        self._kws = kws

        def on_ticks(ws, ticks):
            for t in ticks:
                token = t.get("instrument_token")
                # reverse map token->symbol
                sym = None
                for s, tok in self.tokens_map.items():
                    if int(tok) == int(token):
                        sym = s
                        break
                if not sym:
                    sym = str(token)
                ltp = t.get("last_price") or t.get("last_traded_price") or t.get("ltp")
                if ltp is None:
                    continue
                # try to derive per-tick volume: full mode may include 'volume' or 'last_quantity'
                v = t.get('volume') or t.get('last_quantity') or t.get('last_traded_quantity') or 0
                try: v = float(v)
                except Exception: v = 0.0
                self.on_tick_cb({"symbol": sym, "ltp": float(ltp), "vol": v, "time": now_ist()})

        def on_connect(ws, response):
            self.connected = True
            ws.subscribe(tokens)
            # Use FULL mode to attempt volume fields; fallback handled in bar builder
            try:
                ws.set_mode(ws.MODE_FULL, tokens)
            except Exception:
                ws.set_mode(ws.MODE_LTP, tokens)

        def on_close(ws, code, reason):
            self.connected = False

        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_close = on_close

        # Blocking connect; caller should run in a thread/process if needed.
        kws.connect(threaded=False)

    def stop(self):
        try:
            if self._kws:
                self._kws.close()
        except Exception:
            pass

# ==============================
# Angel SmartWebSocketV2 Runner
# ==============================
class AngelWSRunner:
    def __init__(self, cfg: dict, symbols: Iterable[str], tokens_map: Dict[str, Any], on_tick: Callable[[Dict[str, Any]], None]):
        self.cfg = cfg
        self.symbols = list(symbols)
        self.tokens_map = tokens_map or {}
        self.on_tick_cb = on_tick
        self._ws = None
        self.connected = False

    def _resolve_tokens(self) -> List[str]:
        toks = []
        for s in self.symbols:
            tok = self.tokens_map.get(s)
            if tok is None:
                continue
            toks.append(str(tok))
        return toks

    def start(self):
        try:
            from smartapi.smartWebSocketV2 import SmartWebSocketV2
        except Exception as e:
            self.on_tick_cb({"error": f"smartapi_ws_not_installed: {e}"})
            return

        broker = (self.cfg.get("broker") or {})
        api_key = broker.get("api_key")
        client_id = broker.get("client_id") or broker.get("user_id") or broker.get("userid")
        # Feed token is typically returned by SmartConnect.generateSession / getfeedToken
        feed_token = broker.get("feed_token") or broker.get("feedToken")
        if not (api_key and client_id and feed_token):
            self.on_tick_cb({"error": "missing_angel_ws_credentials (api_key, client_id, feed_token)"})
            return

        tokens = self._resolve_tokens()
        if not tokens:
            self.on_tick_cb({"error": "no_tokens_to_subscribe"})
            return

        ws = SmartWebSocketV2(api_key, client_id, feed_token)
        self._ws = ws

        def on_open(wsapp):
            self.connected = True
            # For each token, subscribe to LTP on NSE by default
            # Angel WS expects JSON strings; refer to SmartWebSocketV2 docs for exact payload
            for tok in tokens:
                sub = {"action": "subscribe", "mode": "LTP", "exchangeType": 1, "tokens": [tok]}
                ws.send(sub)

        def on_data(wsapp, message):
            try:
                data = message.get("data") or {}
                tok = str(data.get("token") or data.get("symbolToken") or "")
                ltp = data.get("ltp") or data.get("last_traded_price") or data.get("price")
                sym = None
                for s, t in self.tokens_map.items():
                    if str(t) == tok:
                        sym = s; break
                if sym and ltp is not None:
                    # try to derive per-tick volume: full mode may include 'volume' or 'last_quantity'
                 v = t.get('volume') or t.get('last_quantity') or t.get('last_traded_quantity') or 0
                try: v = float(v)
                except Exception: v = 0.0
                self.on_tick_cb({"symbol": sym, "ltp": float(ltp), "vol": v, "time": now_ist()})
            except Exception:
                pass

        def on_error(wsapp, error):
            self.on_tick_cb({"error": f"angel_ws_error: {error}"})

        def on_close(wsapp):
            self.connected = False

        ws.on_open = on_open
        ws.on_data = on_data
        ws.on_error = on_error
        ws.on_close = on_close

        # Blocking connect
        ws.connect()

    def stop(self):
        try:
            if self._ws:
                self._ws.close()
        except Exception:
            pass
