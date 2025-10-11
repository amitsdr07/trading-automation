import os
import csv
import time
import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Set, Optional

from zoneinfo import ZoneInfo  # Python 3.9+
from kiteconnect import KiteConnect
from dotenv import load_dotenv

# ========= CONFIG =========
IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dt.time(9, 15)   # 09:15 IST
MARKET_CLOSE = dt.time(15, 30) # 15:30 IST

# Example instrument: INFY (Change as needed)
INSTRUMENT_TOKEN = 256265
INCLUDE_OI = False  # True for futures/options
SLEEP_GRACE_SECONDS = 2
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
        # Convert UTC datetime from Kite to IST
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


def today_ist_bounds() -> (dt.datetime, dt.datetime):
    now_ist = dt.datetime.now(IST)
    open_dt = dt.datetime.combine(now_ist.date(), MARKET_OPEN, tzinfo=IST)
    close_dt = dt.datetime.combine(now_ist.date(), MARKET_CLOSE, tzinfo=IST)
    return open_dt, close_dt


def to_naive_ist(d: dt.datetime) -> dt.datetime:
    """Drop tzinfo so Kite interprets as IST-local naive datetimes."""
    return d.replace(tzinfo=None)


def next_5min_boundary(t: dt.datetime) -> dt.datetime:
    t = t.replace(second=0, microsecond=0)
    minute_mod = t.minute % 5
    if minute_mod == 0:
        return t
    return t + dt.timedelta(minutes=(5 - minute_mod))


def output_filename() -> str:
    """Generate CSV filename with today's date in dd-mm-yyyy format."""
    today_str = dt.datetime.now(IST).strftime("%d-%m-%Y")
    return f"candles_5m_{INSTRUMENT_TOKEN}_{today_str}_IST.csv"


def write_csv_header_if_needed(path: str):
    """Create CSV file with headers if it doesn't exist."""
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            cols = ["date", "time_ist", "datetime_ist", "open", "high", "low", "close", "volume"]
            if INCLUDE_OI:
                cols.append("oi")
            writer.writerow(cols)


def append_new_candles(path: str, candles: List[Candle], seen: Set[str]):
    new_rows = []
    for c in candles:
        # dd-mm-yyyy format for human readability
        date_str = c.date.strftime("%d-%m-%Y")
        time_str = c.date.strftime("%H:%M:%S")
        datetime_str = f"{date_str} {time_str}"

        if datetime_str in seen:
            continue

        row = [
            date_str,
            time_str,
            datetime_str,
            c.open,
            c.high,
            c.low,
            c.close,
            c.volume,
        ]
        if INCLUDE_OI:
            row.append("" if c.oi is None else c.oi)

        new_rows.append((datetime_str, row))

    if not new_rows:
        return 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for key, row in new_rows:
            writer.writerow(row)
            seen.add(key)

    return len(new_rows)


def warm_load_seen(path: str) -> Set[str]:
    seen = set()
    if not os.path.exists(path):
        return seen
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return seen
        datetime_idx = header.index("datetime_ist")
        for row in reader:
            if row and len(row) > datetime_idx:
                seen.add(row[datetime_idx])
    return seen


def fetch_candles_for_today(kite: KiteConnect, token: int) -> List[Candle]:
    open_ist, _ = today_ist_bounds()
    now_ist = dt.datetime.now(IST)
    candles_raw = kite.historical_data(
        instrument_token=token,
        from_date=to_naive_ist(open_ist),
        to_date=to_naive_ist(now_ist),
        interval="5minute",
        continuous=False,
        oi=INCLUDE_OI,
    )
    return [Candle.from_kite_dict(d) for d in candles_raw]


def main():
    filename = output_filename()
    print("📈 Starting 5-minute candle collector (IST + dd-mm-yyyy format)")
    print(f"Instrument token: {INSTRUMENT_TOKEN}")
    print(f"Output file: {filename}")
    print(f"Include OI: {INCLUDE_OI}\n")

    kite = load_env_and_kite()
    write_csv_header_if_needed(filename)
    seen = warm_load_seen(filename)

    open_ist, close_ist = today_ist_bounds()
    now_ist = dt.datetime.now(IST)

    if now_ist < open_ist:
        wait_seconds = (open_ist - now_ist).total_seconds()
        print(f"Waiting for market open ({MARKET_OPEN})... {wait_seconds/60:.1f} min")
        time.sleep(wait_seconds + SLEEP_GRACE_SECONDS)

    while True:
        now_ist = dt.datetime.now(IST)
        if now_ist > close_ist:
            print("Market closed — final fetch and exit.")
            candles = fetch_candles_for_today(kite, INSTRUMENT_TOKEN)
            added = append_new_candles(filename, candles, seen)
            print(f"Added {added} new candle(s). Done.")
            break

        try:
            candles = fetch_candles_for_today(kite, INSTRUMENT_TOKEN)
            added = append_new_candles(filename, candles, seen)
            print(f"[{now_ist.strftime('%H:%M:%S')}] Added {added} new candle(s). Total: {len(seen)}")
        except Exception as e:
            print(f"⚠️ Error fetching/appending: {e}")

        next_tick = next_5min_boundary(now_ist + dt.timedelta(seconds=1))
        sleep_time = (next_tick - now_ist).total_seconds()
        safe_sleep = max(0, sleep_time + SLEEP_GRACE_SECONDS)
        time.sleep(safe_sleep)


if __name__ == "__main__":
    main()
