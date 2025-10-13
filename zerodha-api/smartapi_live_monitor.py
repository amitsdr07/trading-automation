"""SmartAPI live monitoring helper for ORB exits.

Usage:
    from datetime import datetime, timedelta
    from dateutil import tz
    from smartapi_broker import SmartAPIBroker
    from live_monitor import monitor_with_smartapi_ws

    broker = SmartAPIBroker(exchange="NSE", tradingsymbol="RELIANCE", symboltoken="2885")
    until = datetime.utcnow().replace(tzinfo=tz.UTC) + timedelta(minutes=60)
    exit_px, reason = monitor_with_smartapi_ws(broker, side="buy", stop=2500.0, take_profit=2520.0, until_utc=until)
    print(exit_px, reason)

Requirements:
    pip install smartapi-python pyotp websocket-client python-dateutil
"""
from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime
from dateutil import tz
import time


def monitor_with_smartapi_ws(
    broker: "SmartAPIBroker",
    side: str,
    stop: float,
    take_profit: Optional[float],
    until_utc: datetime,
) -> Tuple[float, str]:
    """Block until TP/SL/timeout; returns (exit_price, reason).
    Prefers SmartAPI WebSocket v2 and falls back to LTP polling when WS isn't available.
    """
    last_px = broker.get_last_price(broker.tradingsymbol)
    exit_px = last_px
    reason = "window_end"

    # Try WebSocket V2
    try:
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore
        except Exception:
            from smartapi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore

        if not getattr(broker, "feed_token", None):
            raise RuntimeError("No feed token available for WebSocket.")

        sws = SmartWebSocketV2(broker.api_key, broker.client_id, broker.feed_token)

        token_str = str(getattr(broker, "token", ""))
        if not token_str:
            raise RuntimeError("SmartAPI numeric symbol token is required for WS subscription.")

        done = False

        def on_data(msg):
            nonlocal last_px, exit_px, reason, done
            try:
                ltp = None
                if isinstance(msg, dict):
                    ltp = (
                        msg.get("ltp")
                        or msg.get("last_traded_price")
                        or msg.get("lastPrice")
                        or msg.get("Ltp")
                    )
                if ltp is None and isinstance(msg, (list, tuple)) and msg:
                    try:
                        ltp = float(msg[-1])
                    except Exception:
                        pass
                if ltp is not None:
                    last_px = float(ltp)
                    if side == "buy":
                        if take_profit is not None and last_px >= take_profit:
                            exit_px = take_profit; reason = "take_profit"; done = True
                        elif last_px <= stop:
                            exit_px = stop; reason = "stop_loss"; done = True
                    else:
                        if take_profit is not None and last_px <= take_profit:
                            exit_px = take_profit; reason = "take_profit"; done = True
                        elif last_px >= stop:
                            exit_px = stop; reason = "stop_loss"; done = True
            except Exception:
                pass

        def on_open():
            try:
                sws.subscribe(
                    correlation_id="orb",
                    mode=1,  # 1=LTP in many examples
                    token_list=[{"exchangeType": broker.exchange, "tokens": [token_str]}],
                )
            except Exception:
                exch_map = {"NSE": "nse_cm", "BSE": "bse_cm", "NFO": "nse_fo"}
                sws.subscribe(
                    correlation_id="orb",
                    mode=1,
                    token_list=[f"{exch_map.get(broker.exchange, 'nse_cm')}|{token_str}"],  # type: ignore
                )

        def on_close():
            pass

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_close = on_close

        sws.connect()
        while datetime.utcnow().replace(tzinfo=tz.UTC) < until_utc and not done:
            time.sleep(0.25)
        try:
            sws.close()
        except Exception:
            pass
        if done:
            return exit_px, reason
        return last_px, "window_end"

    except Exception:
        # Fallback: poll LTP once/sec
        while datetime.utcnow().replace(tzinfo=tz.UTC) < until_utc:
            last_px = broker.get_last_price(broker.tradingsymbol)
            if side == "buy":
                if take_profit is not None and last_px >= take_profit:
                    return take_profit, "take_profit"
                if last_px <= stop:
                    return stop, "stop_loss"
            else:
                if take_profit is not None and last_px <= take_profit:
                    return take_profit, "take_profit"
                if last_px >= stop:
                    return stop, "stop_loss"
            time.sleep(1.0)
        return last_px, "window_end"


__all__ = ["monitor_with_smartapi_ws"]
