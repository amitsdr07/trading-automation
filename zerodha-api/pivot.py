import os
import csv
import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Set, Optional

from zoneinfo import ZoneInfo  # Python 3.9+
from kiteconnect import KiteConnect
from dotenv import load_dotenv

# ========= CONFIG =========
IST = ZoneInfo("Asia/Kolkata")
INSTRUMENT_TOKEN = 256265      # e.g., INFY
INCLUDE_OI = False             # True for futures/options
INTERVAL = "15minute"
LOOKBACK_DAYS = 14             # last two weeks
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


def to_naive_ist(d: dt.datetime) -> dt.datetime:
    """Drop tzinfo so Kite interprets as IST-local naive datetimes."""
    return d.replace(tzinfo=None)


def start_of_day_ist(d: dt.datetime) -> dt.datetime:
    return dt.datetime.combine(d.date(), dt.time(0, 0, 0), tzinfo=IST)


def output_filename() -> str:
    end_str = dt.datetime.now(IST).strftime("%d-%m-%Y")
    return f"candles_15m_last2w_{INSTRUMENT_TOKEN}_{end_str}_IST.csv"


def pivots_filename() -> str:
    end_str = dt.datetime.now(IST).strftime("%d-%m-%Y")
    return f"pivots_prevday_last2w_{INSTRUMENT_TOKEN}_{end_str}_IST.csv"


def write_csv_header_if_needed(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            cols = ["date", "time_ist", "datetime_ist", "open", "high", "low", "close", "volume"]
            if INCLUDE_OI:
                cols.append("oi")
            writer.writerow(cols)


def append_rows(path: str, rows: List[List], seen_keys: Set[str]):
    if not rows:
        return 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        added = 0
        for r in rows:
            dt_key = r[2]  # datetime_ist column
            if dt_key in seen_keys:
                continue
            writer.writerow(r)
            seen_keys.add(dt_key)
            added += 1
    return added


def warm_load_seen(path: str) -> Set[str]:
    seen = set()
    if not os.path.exists(path):
        return seen
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return seen
        idx = header.index("datetime_ist")
        for row in reader:
            if row and len(row) > idx:
                seen.add(row[idx])
    return seen


def fetch_candles_range(kite: KiteConnect, token: int) -> List[Candle]:
    now_ist = dt.datetime.now(IST)
    start_ist = start_of_day_ist(now_ist - dt.timedelta(days=LOOKBACK_DAYS))
    end_ist = now_ist
    candles_raw = kite.historical_data(
        instrument_token=token,
        from_date=to_naive_ist(start_ist),
        to_date=to_naive_ist(end_ist),
        interval=INTERVAL,
        continuous=False,
        oi=INCLUDE_OI,
    )
    return [Candle.from_kite_dict(d) for d in candles_raw]


def save_candles_csv(filename: str, candles: List[Candle]) -> int:
    write_csv_header_if_needed(filename)
    seen = warm_load_seen(filename)
    rows = []
    for c in candles:
        date_str = c.date.strftime("%d-%m-%Y")
        time_str = c.date.strftime("%H:%M:%S")
        dt_str = f"{date_str} {time_str}"
        row = [date_str, time_str, dt_str, c.open, c.high, c.low, c.close, c.volume]
        if INCLUDE_OI:
            row.append("" if c.oi is None else c.oi)
        rows.append(row)
    return append_rows(filename, rows, seen)


# ---------- PIVOT CALC (from the saved CSV) ----------

def compute_classic_pivots_from_csv(csv_path: str, out_path: str) -> None:
    """
    For each trading day in CSV, compute pivots for the NEXT day
    using previous day's H/L/C aggregated from 15-minute candles.
    """
    import pandas as pd

    if not os.path.exists(csv_path):
        print(f"⚠️ Candle CSV not found: {csv_path}")
        return

    df = pd.read_csv(csv_path)
    if "datetime_ist" not in df.columns:
        raise ValueError("CSV must contain 'datetime_ist' column.")

    df["datetime_ist"] = pd.to_datetime(df["datetime_ist"], format="%d-%m-%Y %H:%M:%S")
    df["session_date"] = df["datetime_ist"].dt.normalize()

    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"CSV missing required column: {col}")

    day_agg = (df
               .sort_values("datetime_ist")
               .groupby("session_date")
               .agg(H=("high", "max"),
                    L=("low", "min"),
                    C=("close", "last"))
               .sort_index())

    if len(day_agg) < 2:
        print("Not enough sessions to compute previous-day pivots.")
        return

    rows = []
    idx = day_agg.index
    for i in range(1, len(idx)):
        prev_day = idx[i-1]
        apply_day = idx[i]
        H = float(day_agg.loc[prev_day, "H"])
        L = float(day_agg.loc[prev_day, "L"])
        C = float(day_agg.loc[prev_day, "C"])

        P  = (H + L + C) / 3.0
        R1 = 2 * P - L
        S1 = 2 * P - H
        R2 = P + (H - L)
        S2 = P - (H - L)
        R3 = H + 2 * (P - L)
        S3 = L - 2 * (H - P)

        rows.append({
            "apply_date_ist": apply_day.date(),
            "prev_session_ist": prev_day.date(),
            "H_prev": round(H, 4),
            "L_prev": round(L, 4),
            "C_prev": round(C, 4),
            "P": round(P, 4),
            "R1": round(R1, 4), "R2": round(R2, 4), "R3": round(R3, 4),
            "S1": round(S1, 4), "S2": round(S2, 4), "S3": round(S3, 4),
        })

    import pandas as pd
    pivots_df = pd.DataFrame(rows)
    pivots_df.to_csv(out_path, index=False)
    print(f"\n✅ Saved pivots: {out_path}")
    print(pivots_df.to_string(index=False))


def main():
    print(f"🔎 Fetching {INTERVAL} candles for last {LOOKBACK_DAYS} days (IST)…")
    kite = load_env_and_kite()

    candles = fetch_candles_range(kite, INSTRUMENT_TOKEN)
    if not candles:
        print("No candles returned — check instrument token/permissions.")
        return

    candles_path = output_filename()
    added = save_candles_csv(candles_path, candles)
    print(f"💾 Saved/updated: {candles_path}  (+{added} rows)")

    pivots_path = pivots_filename()
    compute_classic_pivots_from_csv(candles_path, pivots_path)


if __name__ == "__main__":
    main()
