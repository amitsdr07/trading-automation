import os
import csv
import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Optional

from zoneinfo import ZoneInfo
from kiteconnect import KiteConnect
from dotenv import load_dotenv

import pandas as pd
import numpy as np

# ========= CONFIG =========
IST = ZoneInfo("Asia/Kolkata")
INSTRUMENT_TOKEN = 256265   # Example: INFY
INCLUDE_OI = False
RSI_PERIOD = 14
INTERVAL = "15minute"
# ==========================


@dataclass
class Candle:
    date: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: Optional[int] = None

    @staticmethod
    def from_kite_dict(d: Dict) -> "Candle":
        date_ist = d["date"].astimezone(IST)
        return Candle(
            date=date_ist,
            open=float(d["open"]),
            high=float(d["high"]),
            low=float(d["low"]),
            close=float(d["close"]),
            volume=int(d.get("volume", 0)),
            oi=(int(d["oi"]) if "oi" in d and d["oi"] is not None else None),
        )


def load_env_and_kite() -> KiteConnect:
    load_dotenv()
    api_key = os.getenv("KITE_API_KEY")
    if not api_key:
        raise RuntimeError("KITE_API_KEY missing in .env")

    with open(".kite_access_token") as f:
        access_token = f.read().strip()

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite


def last_7d_bounds() -> (dt.datetime, dt.datetime):
    now_ist = dt.datetime.now(IST)
    start_ist = now_ist - dt.timedelta(days=7)
    return start_ist, now_ist


def to_naive_ist(d: dt.datetime) -> dt.datetime:
    return d.replace(tzinfo=None)


def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def output_filenames() -> (str, str):
    today_str = dt.datetime.now(IST).strftime("%d-%m-%Y")
    candles_file = f"rsi_candles_15m_{INSTRUMENT_TOKEN}_{today_str}.csv"
    signals_file = f"rsi_signals_{INSTRUMENT_TOKEN}_{today_str}.csv"
    return candles_file, signals_file


def fetch_candles(kite: KiteConnect, token: int) -> List[Candle]:
    start, end = last_7d_bounds()
    candles_raw = kite.historical_data(
        instrument_token=token,
        from_date=to_naive_ist(start),
        to_date=to_naive_ist(end),
        interval=INTERVAL,
        continuous=False,
        oi=INCLUDE_OI,
    )
    return [Candle.from_kite_dict(d) for d in candles_raw]


def save_candles_csv(candles: List[Candle], filename: str):
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        cols = ["datetime_ist", "open", "high", "low", "close", "volume"]
        if INCLUDE_OI:
            cols.append("oi")
        writer.writerow(cols)
        for c in candles:
            row = [c.date.strftime("%d-%m-%Y %H:%M"), c.open, c.high, c.low, c.close, c.volume]
            if INCLUDE_OI:
                row.append("" if c.oi is None else c.oi)
            writer.writerow(row)
    print(f"✅ Saved candle data to {filename}")


def generate_rsi_signals(df: pd.DataFrame) -> pd.DataFrame:
    df["RSI"] = rsi_wilder(df["close"], RSI_PERIOD)
    df["Signal"] = ""

    for i in range(1, len(df)):
        rsi_now, rsi_prev = df.loc[i, "RSI"], df.loc[i - 1, "RSI"]
        if rsi_now > 40 and rsi_now > rsi_prev:
            df.loc[i, "Signal"] = "BUY"
        elif rsi_now < 60 and rsi_now < rsi_prev:
            df.loc[i, "Signal"] = "SELL"

    return df


def save_signals_csv(df: pd.DataFrame, filename: str):
    df = df[df["Signal"] != ""].copy()
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime_ist", "RSI", "Signal", "close"])
        for _, row in df.iterrows():
            writer.writerow([
                row["datetime"].strftime("%d-%m-%Y %H:%M"),
                f"{row['RSI']:.2f}",
                row["Signal"],
                f"{row['close']:.2f}"
            ])
    print(f"✅ Saved RSI signals to {filename}")


def main():
    kite = load_env_and_kite()
    candles, signals = output_filenames()
    print(f"📊 Fetching 15-minute candles for last 7 days...")
    print(f"Instrument token: {INSTRUMENT_TOKEN}")

    candles_data = fetch_candles(kite, INSTRUMENT_TOKEN)
    save_candles_csv(candles_data, candles)

    if not candles_data:
        print("No candle data retrieved.")
        return

    df = pd.DataFrame([{
        "datetime": c.date,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
        "oi": c.oi,
    } for c in candles_data])

    df = df.sort_values("datetime").reset_index(drop=True)
    df = generate_rsi_signals(df)
    save_signals_csv(df, signals)


if __name__ == "__main__":
    main()
