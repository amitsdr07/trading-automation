import os
import csv
import datetime as dt
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from zoneinfo import ZoneInfo
from kiteconnect import KiteConnect
from dotenv import load_dotenv

import pandas as pd
import numpy as np

# ========= CONFIG =========
IST = ZoneInfo("Asia/Kolkata")

INSTRUMENT_TOKEN = 256265
LAST_N_DAYS = 15
INTERVAL = "5minute"

# Indicator params
RSI_PERIOD = 14
BB_WINDOW = 20
BB_NUM_STD = 2.0
EMA_FAST = 9
EMA_SLOW = 15
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Supertrend params
ST_PERIOD = 10
ST_MULT = 3.0

# Thresholds (score in [-100..100])
BUY_THR = 60
SELL_THR = 60

# Positioning behaviour
ALLOW_REVERSE = False   # if True: LONG + SELL desire -> "New Short" (reverse). If False: -> "sell" (exit to FLAT)

INCLUDE_OI = False
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


def last_nd_bounds(n_days: int) -> Tuple[dt.datetime, dt.datetime]:
    now_ist = dt.datetime.now(IST).replace(second=0, microsecond=0)
    start_ist = (now_ist - dt.timedelta(days=n_days)).replace(second=0, microsecond=0)
    return start_ist, now_ist


def to_naive_ist(d: dt.datetime) -> dt.datetime:
    return d.replace(tzinfo=None)


# ===== Indicator utilities =====
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def bollinger(close: pd.Series, window: int = 20, num_std: float = 2.0):
    ma = close.rolling(window).mean()
    std = close.rolling(window).std(ddof=0)
    upper = ma + num_std * std
    lower = ma - num_std * std
    bb_pct_b = (close - lower) / (upper - lower)
    return ma, upper, lower, bb_pct_b

def atr_series(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    hl2 = (df["high"] + df["low"]) / 2.0
    atrv = atr_series(df, period)
    basic_upper = hl2 + multiplier * atrv
    basic_lower = hl2 - multiplier * atrv

    final_upper = pd.Series(np.nan, index=df.index)
    final_lower = pd.Series(np.nan, index=df.index)
    st_dir = pd.Series(1, index=df.index)

    for i in range(len(df)):
        if i == 0:
            final_upper.iat[i] = basic_upper.iat[i]
            final_lower.iat[i] = basic_lower.iat[i]
            st_dir.iat[i] = 1
        else:
            fu_prev = final_upper.iat[i-1]
            fl_prev = final_lower.iat[i-1]
            cu = basic_upper.iat[i]
            cl = basic_lower.iat[i]

            final_upper.iat[i] = cu if (np.isnan(fu_prev) or cu < fu_prev or df["close"].iat[i-1] > fu_prev) else fu_prev
            final_lower.iat[i] = cl if (np.isnan(fl_prev) or cl > fl_prev or df["close"].iat[i-1] < fl_prev) else fl_prev

            if st_dir.iat[i-1] == 1 and df["close"].iat[i] < final_lower.iat[i]:
                st_dir.iat[i] = -1
            elif st_dir.iat[i-1] == -1 and df["close"].iat[i] > final_upper.iat[i]:
                st_dir.iat[i] = 1
            else:
                st_dir.iat[i] = st_dir.iat[i-1]

    st_line = pd.Series(np.where(st_dir == 1, final_lower, final_upper), index=df.index)
    out["ST"] = st_line
    out["ST_DIR"] = st_dir
    out["ST_UPPER"] = final_upper
    out["ST_LOWER"] = final_lower
    return out


# ===== Data fetch =====
def fetch_candles(kite: KiteConnect, token: int) -> List[Candle]:
    start, end = last_nd_bounds(LAST_N_DAYS)
    candles_raw = kite.historical_data(
        instrument_token=token,
        from_date=to_naive_ist(start),
        to_date=to_naive_ist(end),
        interval=INTERVAL,
        continuous=False,
        oi=INCLUDE_OI,
    )
    return [Candle.from_kite_dict(d) for d in candles_raw]


# ===== Signal engine =====
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["EMA9"] = ema(df["close"], EMA_FAST)
    df["EMA15"] = ema(df["close"], EMA_SLOW)
    df["RSI"] = rsi_wilder(df["close"], RSI_PERIOD)

    macd_line, signal_line, hist = macd(df["close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)
    df["MACD"] = macd_line
    df["MACD_SIGNAL"] = signal_line
    df["MACD_HIST"] = hist

    mid, upper, lower, pct_b = bollinger(df["close"], BB_WINDOW, BB_NUM_STD)
    df["BB_MID"] = mid
    df["BB_UPPER"] = upper
    df["BB_LOWER"] = lower
    df["BB_PCTB"] = pct_b

    df["RSI_SLOPE"] = df["RSI"].diff()
    df["MACD_HIST_SLOPE"] = df["MACD_HIST"].diff()
    df["CLOSE_SLOPE"] = df["close"].diff()

    st = supertrend(df, ST_PERIOD, ST_MULT)
    df = pd.concat([df, st], axis=1)
    return df


def indicator_votes(row_prev: pd.Series, row: pd.Series) -> Tuple[float, float, dict]:
    """
    Equal-weight votes (±1.0 each) from:
      RSI(14), EMA(9/15), MACD(12/26/9), Bollinger(20,2), Supertrend(10,3)
    """
    bull = 0.0
    bear = 0.0
    detail = {}

    # RSI
    rsi_now = row["RSI"]; rsi_prev = row_prev["RSI"]
    rsi_rising = (rsi_now > rsi_prev)
    if rsi_now >= 55 and rsi_rising:
        bull += 1.0; detail["RSI"] = "bull"
    elif rsi_now <= 45 and not rsi_rising:
        bear += 1.0; detail["RSI"] = "bear"
    else:
        detail["RSI"] = "neutral"

    # EMA 9/15
    c = row["close"]; e9 = row["EMA9"]; e15 = row["EMA15"]
    if c > e9 > e15:
        bull += 1.0; detail["EMA"] = "bull"
    elif c < e9 < e15:
        bear += 1.0; detail["EMA"] = "bear"
    else:
        detail["EMA"] = "neutral"

    # MACD
    macd_now = row["MACD"]; macd_sig = row["MACD_SIGNAL"]
    hist_now = row["MACD_HIST"]; hist_prev = row_prev["MACD_HIST"]
    hist_rising = hist_now > hist_prev
    if macd_now > macd_sig and hist_rising:
        bull += 1.0; detail["MACD"] = "bull"
    elif macd_now < macd_sig and not hist_rising:
        bear += 1.0; detail["MACD"] = "bear"
    else:
        detail["MACD"] = "neutral"

    # Bollinger (midline)
    if c > row["BB_MID"]:
        bull += 1.0; detail["BB"] = "bull"
    elif c < row["BB_MID"]:
        bear += 1.0; detail["BB"] = "bear"
    else:
        detail["BB"] = "neutral"

    # Supertrend
    st_dir = row.get("ST_DIR", np.nan)
    st_val = row.get("ST", np.nan)
    if pd.notna(st_dir) and pd.notna(st_val):
        if st_dir == 1 and c > st_val:
            bull += 1.0; detail["ST"] = "bull"
        elif st_dir == -1 and c < st_val:
            bear += 1.0; detail["ST"] = "bear"
        else:
            detail["ST"] = "neutral"
    else:
        detail["ST"] = "neutral"

    return bull, bear, detail


def score_to_signal(total_bull: float, total_bear: float, buy_thr: float = BUY_THR, sell_thr: float = SELL_THR):
    """
    Map votes to [-100..+100] score and a directional desire: BUY / SELL / HOLD.
    """
    max_points = 5.0
    raw = total_bull - total_bear
    score = max(-100.0, min(100.0, (raw / max_points) * 100.0))

    if score >= buy_thr:
        return "BUY", score
    elif score <= -sell_thr:
        return "SELL", abs(score)
    else:
        return "HOLD", abs(score)


def build_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds stateful Position + emits:
      - "New Long"  : open long from FLAT (or flip from SHORT)
      - "New Short" : open short from FLAT
      - "sell"      : exit long to FLAT (no same-bar short unless ALLOW_REVERSE=True)
      - "HOLD"      : otherwise
    """
    df = df.copy()
    df["BullPoints"] = np.nan
    df["BearPoints"] = np.nan
    df["RawDesire"] = ""      # BUY/SELL/HOLD (pre-state)
    df["Signal"] = ""         # New Long / New Short / sell / HOLD
    df["Confidence"] = np.nan
    df["Votes"] = ""
    df["Position"] = "FLAT"

    position = "FLAT"

    for i in range(1, len(df)):
        bull, bear, detail = indicator_votes(df.iloc[i-1], df.iloc[i])
        desire, conf = score_to_signal(bull, bear, buy_thr=BUY_THR, sell_thr=SELL_THR)

        out_sig = "HOLD"
        # stateful mapping
        if desire == "BUY":
            if position == "FLAT":
                out_sig = "New Long"
                position = "LONG"
            elif position == "SHORT":
                out_sig = "New Long"   # flip short -> long
                position = "LONG"
            else:  # already LONG
                out_sig = "HOLD"

        elif desire == "SELL":
            if position == "FLAT":
                out_sig = "New Short"
                position = "SHORT"
            elif position == "LONG":
                if ALLOW_REVERSE:
                    out_sig = "New Short"  # reverse long -> short
                    position = "SHORT"
                else:
                    out_sig = "sell"       # exit long only
                    position = "FLAT"
            else:  # already SHORT
                out_sig = "HOLD"

        # write row
        df.loc[i, "BullPoints"] = bull
        df.loc[i, "BearPoints"] = bear
        df.loc[i, "RawDesire"] = desire
        df.loc[i, "Signal"] = out_sig
        df.loc[i, "Confidence"] = round(conf, 1)
        df.loc[i, "Votes"] = "|".join(f"{k}:{v}" for k, v in detail.items())
        df.loc[i, "Position"] = position

    return df


# ===== Output helpers =====
def output_filenames() -> Tuple[str, str]:
    today_str = dt.datetime.now(IST).strftime("%d-%m-%Y")
    candles_file = f"multiind_candles_5m_{INSTRUMENT_TOKEN}_{today_str}.csv"
    signals_file = f"multiind_signals_5m_{INSTRUMENT_TOKEN}_{today_str}.csv"
    return candles_file, signals_file


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
    print(f"✅ Saved {filename}")


def save_signals_csv(df: pd.DataFrame, filename: str):
    out = df[["datetime", "close",
              "RSI", "EMA9", "EMA15", "MACD", "MACD_SIGNAL", "MACD_HIST",
              "BB_MID", "BB_UPPER", "BB_LOWER",
              "ST", "ST_DIR",
              "BullPoints", "BearPoints", "RawDesire",
              "Signal", "Confidence", "Votes", "Position"]].copy()
    out.rename(columns={"datetime": "datetime_ist"}, inplace=True)
    out["datetime_ist"] = out["datetime_ist"].dt.strftime("%d-%m-%Y %H:%M")
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(out.columns)
        for _, r in out.iterrows():
            writer.writerow(list(r.values))
    print(f"✅ Saved {filename}")


# ===== Main =====
def main():
    kite = load_env_and_kite()
    candles_file, signals_file = output_filenames()

    print(f"📊 Fetching {INTERVAL} candles for last {LAST_N_DAYS} days (token={INSTRUMENT_TOKEN}) ...")
    candles = fetch_candles(kite, INSTRUMENT_TOKEN)
    if not candles:
        print("No candle data retrieved.")
        return

    save_candles_csv(candles, candles_file)

    df = pd.DataFrame([{
        "datetime": c.date,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
        "oi": c.oi
    } for c in candles]).sort_values("datetime").reset_index(drop=True)

    market_open = dt.time(9, 15)
    market_close = dt.time(15, 30)
    df = df[(df["datetime"].dt.time >= market_open) & (df["datetime"].dt.time <= market_close)].copy()

    df = compute_indicators(df)
    df = build_signals(df)

    save_signals_csv(df, signals_file)

    # Quick console preview
    tail = df[["datetime","close","RSI","EMA9","EMA15","MACD","MACD_SIGNAL","MACD_HIST",
               "ST","ST_DIR","RawDesire","Signal","Confidence","Position"]].tail(12)
    print("\nLast rows preview:")
    for _, r in tail.iterrows():
        print(f"{r['datetime'].strftime('%d-%m %H:%M')} | Close={r['close']:.2f} "
              f"| RSI={r['RSI']:.1f} | EMA9={r['EMA9']:.2f} | EMA15={r['EMA15']:.2f} "
              f"| MACD={r['MACD']:.4f}/{r['MACD_SIGNAL']:.4f} | ST={r['ST']:.2f} "
              f"| DIR={int(r['ST_DIR']) if pd.notna(r['ST_DIR']) else '-'} "
              f"| desire={r['RawDesire']} -> {r['Signal']} [{r['Confidence']:.0f}] | pos={r['Position']}")

if __name__ == "__main__":
    main()
