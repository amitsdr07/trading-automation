#!/usr/bin/env python3
"""
Open Range Breakout (ORB) strategy – 1‑Hour Trading Window

Features
- Defines the open range using the first `range_minutes` after session open.
- Enters long on breakout above the range high; short on breakdown below the range low (first signal only).
- Stop-loss at the opposite side of the opening range.
- Optional take-profit at `tp_multiple` × opening-range size.
- Always exits any open position at the end of the 1‑hour trading window.
- Works in DRY-RUN (default) or ALPACA live/paper modes.
- Designed to be scheduled once per trading day (e.g., with cron/systemd).

Dependencies
    pip install pandas numpy yfinance pytz python-dateutil requests kiteconnect smartapi-python pyotp websocket-client

Quick start (dry-run / paper backfill using today’s data):
    python orb_trader.py --symbol AAPL --market ET --open 09:30 --range-minutes 15 --window-minutes 60 --tp-multiple 1.0 --risk 0.01

Alpaca mode (set env vars):
    export ALPACA_API_KEY_ID=... 
    export ALPACA_API_SECRET_KEY=...
    export ALPACA_BASE_URL=https://paper-api.alpaca.markets  # or live

    python orb_trader.py --symbol AAPL --broker alpaca --qty 10 --market ET --open 09:30

Scheduling (cron example – run at 14:30 London time for NYSE open during winter):
    # Edit with: crontab -e
    # ┌───────── min (0-59)
    # │ ┌────── hour (0-23)
    # │ │ ┌──── day of month
    # │ │ │ ┌── month
    # │ │ │ │ ┌ day of week (0=Sun)
    # │ │ │ │ │
    # 30 14 * * 1-5 /usr/bin/python3 /path/to/orb_trader.py --symbol AAPL --market ET --open 09:30 >> /path/to/log.txt 2>&1

Notes
- This script fetches 1‑minute bars via yfinance (for backfill). During true live trading, use your broker’s market data.
- Timezone handling: choose market shorthand `ET`, `London`, `UTC`, or pass an IANA tz name via --tz.
"""

from __future__ import annotations
import os
import sys
import math
import time
import json
import argparse
from dataclasses import dataclass
import csv
from typing import Optional, Literal
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yaml
#import yfinance as yf
from dateutil import tz
from smartapi_broker import SmartAPIBroker
from smartapi_live_monitor import monitor_with_smartapi_ws
from kite_broker import KiteBroker, get_kite_instrument_token, fetch_intraday_kite
from kite_live_monitor import monitor_with_kite_ws


# --------------------------- Utility ---------------------------------
TZ_ALIASES = {
    "ET": "America/New_York",
    "Eastern": "America/New_York",
    "NewYork": "America/New_York",
    "London": "Europe/London",
    "UK": "Europe/London",
    "UTC": "UTC",
}


def parse_time_str(t: str) -> tuple[int, int]:
    hh, mm = t.split(":")
    return int(hh), int(mm)


def now_utc() -> datetime:
    return datetime.utcnow().replace(tzinfo=tz.UTC)


@dataclass
class ORBParams:
    symbol: str
    market_open: str  # HH:MM local to market tz
    market_tz: str
    range_minutes: int = 15
    window_minutes: int = 60
    tp_multiple: Optional[float] = None  # e.g., 1.0 × range
    risk_fraction: float = 0.01  # fraction of equity to risk (dry-run sizing)
    qty: Optional[float] = None  # if provided, overrides sizing
    broker: Literal["dry", "alpaca"] = "dry"


# --------------------------- Broker Abstraction -----------------------
class Broker:
    def place_order(self, symbol: str, side: str, qty: float, order_type: str = "market"):
        raise NotImplementedError

    def close_position(self, symbol: str):
        book = self.smart.position()
        qty = 0
        product = "INTRADAY"
        if book and book.get("data"):
            for p in book["data"]:
                if p.get("tradingsymbol") == self.tradingsymbol and p.get("exchange") == self.exchange and int(p.get("netqty", 0)) != 0:
                    qty = int(p.get("netqty", 0))
                    product = p.get("producttype", "INTRADAY")
                    break
        if qty == 0:
            print("[SMARTAPI] No open position to close.")
            return
        side = "BUY" if qty < 0 else "SELL"
        orderparams = {
            "variety": "NORMAL",
            "tradingsymbol": self.tradingsymbol,
            "symboltoken": str(self.token) if self.token else None,
            "transactiontype": side,
            "exchange": self.exchange,
            "ordertype": "MARKET",
            "producttype": product,
            "duration": "DAY",
            "quantity": abs(qty),
        }
        orderparams = {k: v for k, v in orderparams.items() if v is not None}
        self.smart.placeOrder(orderparams)
        print(f"[SMARTAPI] Flattened {product} position with market order.")
        if not resp or not resp.get("status"):
            raise RuntimeError(f"SmartAPI order error: {resp}")
        return resp

    def close_position(self, symbol: str):
        book = self.smart.position()
        qty = 0
        if book and book.get("data"):
            for p in book["data"]:
                if p.get("tradingsymbol") == self.tradingsymbol and p.get("exchange") == self.exchange and p.get("producttype") in ("INTRADAY","DELIVERY"):
                    qty = int(p.get("netqty", 0))
                    break
        if qty == 0:
            print("[SMARTAPI] No open position to close.")
            return
        side = "BUY" if qty < 0 else "SELL"
        orderparams = {
            "variety": "NORMAL",
            "tradingsymbol": self.tradingsymbol,
            "symboltoken": str(self.token) if self.token else None,
            "transactiontype": side,
            "exchange": self.exchange,
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "quantity": abs(qty),
        }
        orderparams = {k: v for k, v in orderparams.items() if v is not None}
        self.smart.placeOrder(orderparams)

    def get_last_price(self, symbol: str) -> float:
        try:
            data = self.smart.ltpData(self.exchange, self.tradingsymbol, str(self.token) if self.token else None)
            return float(data["data"]["ltp"])
        except Exception:
            data = self.smart.ltpData(exchange=self.exchange, tradingsymbol=self.tradingsymbol, symboltoken=str(self.token) if self.token else None)
            return float(data["data"]["ltp"])  # type: ignore

    # --- GTT (OCO) ---
    def create_gtt_oco(self, side: str, qty: int, stop_price: float, target_price: float, product: str = "DELIVERY"):
        payload = {
            "tradingsymbol": self.tradingsymbol,
            "symboltoken": str(self.token) if self.token else None,
            "exchange": self.exchange,
            "transactiontype": "BUY" if side == "buy" else "SELL",
            "producttype": product,
            "quantity": int(qty),
            "price": 0,
            "triggerprice": 0,
            "timeperiod": 365,
            "type": "OCO",
            "priceband": [target_price, stop_price],
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        try:
            fn = getattr(self.smart, "gttCreateRule")
            resp = fn(payload)
            if resp and resp.get("status"):
                return resp
        except Exception:
            pass
        try:
            resp = self.smart.createGttRule(payload)  # type: ignore
            if resp and resp.get("status"):
                return resp
        except Exception as e:
            raise RuntimeError(f"GTT OCO creation failed: {e}")

    def cancel_all_gtt_for_symbol(self):
        try:
            rules = None
            try:
                rules = self.smart.gttGetRuleList()
            except Exception:
                rules = self.smart.getGttRuleList()  # type: ignore
            if not rules or not rules.get("data"):
                return
            for r in rules["data"]:
                ts = r.get("tradingsymbol") or r.get("symbolname")
                rid = r.get("id") or r.get("rule_id")
                if ts == self.tradingsymbol and rid:
                    try:
                        try:
                            self.smart.gttDeleteRule({"id": rid})
                        except Exception:
                            self.smart.cancelGttRule({"id": rid})  # type: ignore
                    except Exception:
                        pass
        except Exception:
            pass


def fetch_intraday_smartapi(smart, exchange: str, tradingsymbol: str, token: Optional[str], d0: datetime, d1: datetime) -> pd.DataFrame:
    fmt = "%Y-%m-%d %H:%M"
    params = {"exchange": exchange, "symboltoken": str(token) if token else None, "interval": "ONE_MINUTE", "fromdate": d0.strftime(fmt), "todate": d1.strftime(fmt)}
    params = {k: v for k, v in params.items() if v is not None}
    try:
        raw = smart.getCandleData(params)
    except Exception:
        raw = smart.historicalData(params)  # type: ignore
    if not raw or not raw.get("data"):
        raise RuntimeError("No historical data from SmartAPI for requested window.")
    arr = raw["data"]
    df = pd.DataFrame(arr, columns=["time","open","high","low","close","volume"])
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time"]).set_index("time")
    df = df.loc[(df.index >= d0) & (df.index <= d1)].copy()
    if df.empty:
        raise RuntimeError("No bars in the requested window (SmartAPI).")
    return df

# --------------------------- Live WebSocket (SmartAPI) ---------------

def monitor_with_smartapi_ws(broker: "SmartAPIBroker", side: str, stop: float, take_profit: Optional[float], until_utc: datetime) -> tuple[float, str]:
    """Block until TP/SL/timeout; returns (exit_px, reason). Uses WebSocket2 if available, falls back to polling LTP."""
    last_px = broker.get_last_price(broker.tradingsymbol)
    reason = "window_end"
    exit_px = last_px
    try:
        try:
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
        except Exception:
            from smartapi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore
        if not broker.feed_token:
            raise RuntimeError("No feed token available for WebSocket.")
        sws = SmartWebSocketV2(broker.api_key, broker.client_id, broker.feed_token)
        token = str(broker.token) if broker.token else None
        if token is None:
            raise RuntimeError("SmartAPI token required for WS subscription.")

        done = False
        def on_data(msg):
            nonlocal last_px, exit_px, reason, done
            try:
                # message shapes differ; try common fields
                ltp = None
                if isinstance(msg, dict):
                    ltp = msg.get("ltp") or msg.get("last_traded_price") or msg.get("lastPrice")
                if ltp is None and isinstance(msg, (list, tuple)) and msg:
                    ltp = msg[-1]
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
            # mode 1=LTP in many examples; subscription list uses "exchange|token"
            try:
                sws.subscribe(correlation_id="orb", mode=1, token_list=[{"exchangeType": broker.exchange, "tokens": [str(broker.token)]}])
            except Exception:
                # fallback older signature
                exch_map = {"NSE":"nse_cm","BSE":"bse_cm","NFO":"nse_fo"}
                sws.subscribe(correlation_id="orb", mode=1, token_list=[f"{exch_map.get(broker.exchange,'nse_cm')}|{broker.token}"])  # type: ignore

        def on_close():
            pass

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_close = on_close

        sws.connect()
        # Run until timeout
        while datetime.utcnow().replace(tzinfo=tz.UTC) < until_utc and not done:
            time.sleep(0.25)
        try:
            sws.close()
        except Exception:
            pass
        return exit_px, reason if done else (last_px, "window_end")
    except Exception:
        # Fallback polling
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
            time.sleep(1)
        return last_px, "window_end"

# --------------------------- Logging helpers -------------------------

def append_log_row(csv_path: str, row: dict):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True) if os.path.dirname(csv_path) else None
    file_exists = os.path.isfile(csv_path)
    with open(csv_path, mode="a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# --------------------------- ORB Core --------------------------------
@dataclass
class ORBState:
    
    range_high: float
    range_low: float
    entered: bool
    side: Optional[str]
    entry_price: Optional[float]
    stop: Optional[float]
    take_profit: Optional[float]
    qty: Optional[int] = None


def fetch_intraday_yf(symbol: str, d0: datetime, d1: datetime) -> pd.DataFrame:
    """Fetch 1‑minute bars from yfinance between [d0, d1] in UTC."""
    df = yf.download(symbol, interval="1m", period="5d", auto_adjust=False, progress=False)
    if df.empty:
        raise RuntimeError("No data returned from yfinance. Try another symbol or run during market hours.")
    df = df.tz_localize("UTC") if df.tz is None else df.tz_convert("UTC")
    df = df.loc[(df.index >= d0) & (df.index <= d1)].copy()
    df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
    if df.empty:
        raise RuntimeError("No bars in the requested window.")
    return df


def fetch_intraday_kite(kite, instrument_token: int, d0: datetime, d1: datetime) -> pd.DataFrame:
    """Fetch 1‑minute bars from Kite historical API (requires appropriate plan)."""
    start = d0.replace(tzinfo=None)
    end = d1.replace(tzinfo=None)
    data = kite.historical_data(instrument_token, start, end, interval="minute", oi=False)
    if not data:
        raise RuntimeError("No historical data from Kite for the requested window.")
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df.set_index("date", inplace=True)
    df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}, inplace=True)
    df = df.loc[(df.index >= d0) & (df.index <= d1)].copy()
    if df.empty:
        raise RuntimeError("No bars in the requested window (Kite).")
    return df


def get_kite_instrument_token(kite, exchange: str, tradingsymbol: str) -> int:
    ins = kite.instruments(exchange)
    for row in ins:
        if row.get("tradingsymbol") == tradingsymbol:
            return int(row["instrument_token"])
    raise RuntimeError(f"tradingsymbol {tradingsymbol} not found on {exchange}")


def compute_open_range(bars: pd.DataFrame, open_ts: datetime, range_minutes: int) -> tuple[pd.DataFrame, float, float]:
    range_end = open_ts + timedelta(minutes=range_minutes)
    rng = bars.loc[(bars.index >= open_ts) & (bars.index < range_end)]
    if rng.empty:
        raise RuntimeError("No bars found during the opening range window.")
    return rng, float(rng.high.max()), float(rng.low.min())


def first_breakout_signal(bars: pd.DataFrame, after_ts: datetime, until_ts: datetime, hi: float, lo: float) -> Optional[tuple[datetime, str, float]]:
    """Return (timestamp, side, price) of the first breakout candle close between after_ts and until_ts."""
    window = bars.loc[(bars.index >= after_ts) & (bars.index <= until_ts)]
    for ts, row in window.iterrows():
        if row["close"] > hi:
            return ts, "buy", float(row["close"])  # long
        if row["close"] < lo:
            return ts, "sell", float(row["close"])  # short
    return None


def position_size(equity: float, risk_fraction: float, entry: float, stop: float) -> int:
    risk_per_share = abs(entry - stop)
    if risk_per_share <= 0:
        return 0
    qty = int(max(1, math.floor((equity * risk_fraction) / risk_per_share)))
    return qty


def run_orb(params: ORBParams):
    mkt_tz = tz.gettz(TZ_ALIASES.get(params.market_tz, params.market_tz))
    if mkt_tz is None:
        raise RuntimeError(f"Unknown timezone {params.market_tz}")

    # Determine session timestamps in UTC for today (market tz aware)
    #today_market = datetime.now(tz=mkt_tz).date()
    today_market = (datetime.now(tz=mkt_tz) - timedelta(days=1)).date()

    h, m = parse_time_str(params.market_open)
    open_ts_local = datetime(today_market.year, today_market.month, today_market.day, h, m, tzinfo=mkt_tz)
    end_ts_local = open_ts_local + timedelta(minutes=params.window_minutes)
    #d0_utc = open_ts_local.astimezone(tz.UTC) - timedelta(minutes=params.range_minutes + 5)
    #d1_utc = end_ts_local.astimezone(tz.UTC) + timedelta(minutes=5)
    d0_ist = open_ts_local - timedelta(minutes=params.range_minutes + 5)
    d1_ist = end_ts_local + timedelta(minutes=5)

    print(open_ts_local)
    print(end_ts_local)
    print(d0_ist)
    print(d1_ist)

    # Data source: SmartAPI, Kite, or yfinance
    if params.broker == "smartapi":
        sab = SmartAPIBroker(getattr(params, "exchange", "NSE"), params.symbol, getattr(params, "token", None))
        bars = fetch_intraday_smartapi(sab.smart, getattr(params, "exchange", "NSE"), params.symbol, getattr(params, "token", None), d0_ist, d1_ist)
    elif params.broker == "kite":
        kb = KiteBroker(getattr(params, "exchange", "NSE"), params.symbol)
        instrument_token = get_kite_instrument_token(kb.kite, getattr(params, "exchange", "NSE"), params.symbol)
        bars = fetch_intraday_kite(kb.kite, instrument_token, d0_ist, d1_ist)

    # Build state
    _, hi, lo = compute_open_range(bars, open_ts_local.astimezone(tz.UTC), params.range_minutes)
    rng_size = hi - lo

    # Prepare broker
    price_lookup = lambda: float(bars.iloc[-1].close)
    broker: Broker
    if params.broker == "smartapi":
        broker = SmartAPIBroker(getattr(params, "exchange", "NSE"), params.symbol, getattr(params, "token", None))
    elif params.broker == "kite":
        try:
            broker = kb  # defined above when fetching data
        except NameError:
            broker = KiteBroker(getattr(params, "exchange", "NSE"), params.symbol)
    else:
        broker = DryRunBroker(price_lookup)

    # Find first breakout in the trading window AFTER the range ends
    signal = first_breakout_signal(
        bars,
        after_ts=open_ts_local.astimezone(tz.UTC) + timedelta(minutes=params.range_minutes),
        until_ts=end_ts_local.astimezone(tz.UTC),
        hi=hi,
        lo=lo,
    )

    # Initialize state
    state = ORBState(range_high=hi, range_low=lo, entered=False, side=None, entry_price=None, stop=None, take_profit=None)

    equity_assumed = 25_000  # for dry-run sizing if qty not provided

    if signal:
        ts, side, px = signal
        stop = lo if side == "buy" else hi
        tp = None
        if params.tp_multiple is not None:
            tp = px + params.tp_multiple * rng_size if side == "buy" else px - params.tp_multiple * rng_size

        # Qty decision
        if params.qty is not None:
            qty = int(params.qty)
        else:
            qty = position_size(equity_assumed, params.risk_fraction, px, stop)
            if qty <= 0:
                qty = 1

        broker.place_order(params.symbol, side, qty)
        state.entered = True
        state.side = side
        state.entry_price = px
        state.stop = stop
        state.take_profit = tp
        state.qty = int(qty)
        print(f"Entered {side.upper()} at {px:.4f} | stop {stop:.4f} | tp {tp if tp is not None else '—'}")

        # Monitor within remaining window: prefer SmartAPI WebSocket if requested and available
        exit_reason = "window_end"
        exit_px = px
        if isinstance(broker, SmartAPIBroker) and getattr(params, "live_ws", False):
            exit_px, exit_reason = monitor_with_smartapi_ws(broker, state.side, state.stop, state.take_profit, end_ts_local.astimezone(tz.UTC))
        else:
            monitor = bars.loc[(bars.index > ts) & (bars.index <= end_ts_local.astimezone(tz.UTC))]
            exit_px = float(monitor.iloc[-1].close) if not monitor.empty else px
            for _, row in monitor.iterrows():
                price_h = float(row.get("high", row["close"]))
                price_l = float(row.get("low", row["close"]))
                if state.side == "buy":
                    if state.take_profit is not None and price_h >= state.take_profit:
                        exit_px = state.take_profit
                        exit_reason = "take_profit"
                        break
                    if price_l <= state.stop:
                        exit_px = state.stop
                        exit_reason = "stop_loss"
                        break
                else:
                    if state.take_profit is not None and price_l <= state.take_profit:
                        exit_px = state.take_profit
                        exit_reason = "take_profit"
                        break
                    if price_h >= state.stop:
                        exit_px = state.stop
                        exit_reason = "stop_loss"
                        break

        # If requested, cancel any standing GTTs before forced flatten
        if getattr(params, "force_close_at_window_end", False) and isinstance(broker, SmartAPIBroker):
            try:
                broker.cancel_all_gtt_for_symbol()
                print("[SMARTAPI] Cancelled any existing GTT rules for symbol before flattening.")
            except Exception as e:
                print(f"[SMARTAPI] GTT cancel attempt failed: {e}")

        broker.close_position(params.symbol)
        print(f"Exit {params.symbol} @ ~{exit_px:.4f} due to {exit_reason}")
        pnl = (exit_px - state.entry_price) * (1 if state.side == "buy" else -1)
        print(f"PnL per share: {pnl:.4f}")
        # --- CSV logging for trade day
        try:
            log_row = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "broker": params.broker,
                "symbol": params.symbol,
                "exchange": getattr(params, "exchange", ""),
                "side": state.side,
                "qty": state.qty,
                "entry": state.entry_price,
                "exit": exit_px,
                "stop": state.stop,
                "take_profit": state.take_profit,
                "reason": exit_reason,
                "pnl_per_share": pnl,
                "pnl_total": (pnl * (state.qty or 0)),
                "range_high": state.range_high,
                "range_low": state.range_low,
                "range_minutes": params.range_minutes,
                "window_minutes": params.window_minutes,
            }
            append_log_row(getattr(params, "log_file", "orb_trades.csv"), log_row)
            print(f"[LOG] Appended to {getattr(params, 'log_file', 'orb_trades.csv')}")
        except Exception as e:
            print(f"[LOG] Failed to write CSV: {e}")
    else:
        print("No breakout signal within the trading window. No trades placed.")
        # --- CSV logging for no-trade day
        try:
            log_row = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "broker": params.broker,
                "symbol": params.symbol,
                "exchange": getattr(params, "exchange", ""),
                "side": None,
                "qty": 0,
                "entry": None,
                "exit": None,
                "stop": None,
                "take_profit": None,
                "reason": "no_signal",
                "pnl_per_share": 0,
                "pnl_total": 0,
                "range_high": state.range_high,
                "range_low": state.range_low,
                "range_minutes": params.range_minutes,
                "window_minutes": params.window_minutes,
            }
            append_log_row(getattr(params, "log_file", "orb_trades.csv"), log_row)
            print(f"[LOG] Appended no-trade row to {getattr(params, 'log_file', 'orb_trades.csv')}")
        except Exception as e:
            print(f"[LOG] Failed to write CSV: {e}")

    # Summary
    summary = {
        "symbol": params.symbol,
        "range_high": state.range_high,
        "range_low": state.range_low,
        "range_size": rng_size,
        "entered": state.entered,
        "side": state.side,
        "entry": state.entry_price,
        "stop": state.stop,
        "take_profit": state.take_profit,
        "window_minutes": params.window_minutes,
        "range_minutes": params.range_minutes,
    }
    print("\nJSON_SUMMARY\n" + json.dumps(summary, indent=2))


# --------------------------- CLI -------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Open Range Breakout – 1‑hour window")
    p.add_argument("--symbol", required=True, help="Symbol: for Kite/SmartAPI use TRADING SYMBOL (e.g., RELIANCE, INFY)")
    p.add_argument("--exchange", default="NSE", help="Exchange for Kite/SmartAPI (e.g., NSE, BSE, NFO)")
    p.add_argument("--token", default=None, help="Symbol token for SmartAPI (recommended)")
    p.add_argument("--product", default="INTRADAY", choices=["INTRADAY","DELIVERY"], help="Order product type")
    p.add_argument("--use-gtt", action="store_true", help="For DELIVERY product, create OCO GTT for stop & target")
    p.add_argument("--force-close-at-window-end", action="store_true", help="Cancel any GTTs and flatten position at window end")
    p.add_argument("--live-ws", action="store_true", help="Use SmartAPI WebSocket for live monitoring (faster exits)")
    p.add_argument("--open", dest="market_open", default="09:30", help="Market open time HH:MM in market tz")
    p.add_argument("--market", dest="market_tz", default="ET", help="Market tz alias: ET, London, UTC or IANA name")
    p.add_argument("--tz", dest="tz_override", default=None, help="Override timezone with an IANA tz name")
    p.add_argument("--range-minutes", type=int, default=15)
    p.add_argument("--window-minutes", type=int, default=60)
    p.add_argument("--tp-multiple", type=float, default=None, help="Take-profit multiple of opening range (e.g., 1.0)")
    p.add_argument("--risk", dest="risk_fraction", type=float, default=0.01, help="Risk fraction of equity for sizing (dry-run)")
    p.add_argument("--qty", type=float, default=None, help="Fixed quantity to trade (overrides sizing)")
    p.add_argument("--log-file", default="orb_trades.csv", help="CSV path to append trade logs")
    p.add_argument("--broker", choices=["dry", "kite", "smartapi"], default="dry")
    return p

def load_config(path: str) -> dict:
    """
    Load YAML or JSON config file.
    """
    if not path or not os.path.isfile(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    lower = path.lower()
    if lower.endswith((".yml", ".yaml")):
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    elif lower.endswith(".json"):
        with open(path, "r") as f:
            return json.load(f) or {}
    else:
        raise RuntimeError("Unsupported config format. Use .yml/.yaml or .json")


def apply_config_to_env(cfg: dict):
    """
    Apply environment variables from config['env'] if present.
    """
    env_vars = cfg.get("env", {}) if isinstance(cfg, dict) else {}
    for k, v in env_vars.items():
        if k and v is not None:
            os.environ[k] = str(v)
            print(f"[ENV] Set {k}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Open Range Breakout – 1-hour window")
    parser.add_argument(
        "--config",
        default="orb-config.yml",
        help="Config file name (YAML or JSON) in the same directory",
    )
    args = parser.parse_args()

    # --- Resolve full path for config ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, args.config)
    if not os.path.isfile(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    print(f"[CONFIG] Loading {config_path}")
    cfg = load_config(config_path)
    apply_config_to_env(cfg)

    # Extract parameters
    params_cfg = cfg.get("params", {})
    required_fields = ["symbol", "broker", "market", "open"]
    for field in required_fields:
        if field not in params_cfg:
            raise KeyError(f"Missing required field in config: params.{field}")

    tz_name = params_cfg.get("tz_override", params_cfg.get("market"))
    params = ORBParams(
        symbol=params_cfg["symbol"].upper(),
        market_open=params_cfg.get("open", "09:15"),
        market_tz=tz_name,
        range_minutes=params_cfg.get("range_minutes", 15),
        window_minutes=params_cfg.get("window_minutes", 60),
        tp_multiple=params_cfg.get("tp_multiple"),
        risk_fraction=params_cfg.get("risk_fraction", 0.01),
        qty=params_cfg.get("qty"),
        broker=params_cfg.get("broker", "smartapi"),
    )

    # Optional parameters
    setattr(params, "exchange", params_cfg.get("exchange", "NSE"))
    setattr(params, "product", params_cfg.get("product", "INTRADAY"))
    setattr(params, "live_ws", params_cfg.get("live_ws", False))
    setattr(params, "force_close_at_window_end", params_cfg.get("force_close_at_window_end", True))
    setattr(params, "token", params_cfg.get("token"))
    setattr(params, "log_file", params_cfg.get("log_file", "orb_trades.csv"))

    print(f"[INFO] Starting ORB strategy for {params.symbol} on {params.exchange} via {params.broker.upper()}")
    run_orb(params)
