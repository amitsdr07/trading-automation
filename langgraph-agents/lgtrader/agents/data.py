from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import math

# --- Ensure a valid CA bundle for HTTPS (fixes curl: (60) SSL issues) ---
try:
    import certifi  # type: ignore
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    # If certifi is not available, we just proceed; but it's strongly recommended to install it.
    pass

# yfinance is used for market data
import yfinance as yf  # type: ignore


# --------------------------------------------------------------------------------------
# Small result carrier to match your agents' .run() contract (summary + details)
# --------------------------------------------------------------------------------------
@dataclass
class AgentResult:
    summary: str
    details: Dict[str, Any]


# --------------------------------------------------------------------------------------
# Helpers: symbol mapping for Yahoo Finance (NSE equities + indices)
# --------------------------------------------------------------------------------------
INDEX_ALIASES: Dict[str, str] = {
    # Commons people sometimes pass in:
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY_50": "^NSEI",
    "NSE": "^NSEI",
    "NSEI": "^NSEI",
    "BANKNIFTY": "^NSEBANK",
    "NIFTYBANK": "^NSEBANK",
    "BANK_NIFTY": "^NSEBANK",
}

def to_yahoo_symbol(sym: str) -> str:
    """
    Map a user symbol to a Yahoo Finance symbol.
    - Indian equities need '.NS' suffix.
    - Common index aliases mapped to '^NSEI' or '^NSEBANK'.
    """
    s = (sym or "").strip().upper()
    if not s:
        return s
    # Known index aliases
    if s in INDEX_ALIASES:
        return INDEX_ALIASES[s]
    # If it already looks like a Yahoo index symbol, keep it
    if s.startswith("^"):
        return s
    # If it already has a suffix (e.g., .NS), leave it
    if "." in s:
        return s
    # Default: assume NSE equity and append .NS
    return s + ".NS"


# --------------------------------------------------------------------------------------
# Market News Agent (stub) – included so your imports work
# Replace this with your real implementation as needed.
# --------------------------------------------------------------------------------------
class MarketNewsAgent:
    def __init__(self, cfg: Dict[str, Any] | None = None):
        self.cfg = cfg or {}

    def run(self, payload: Dict[str, Any]) -> AgentResult:
        # Stubbed; you can integrate NewsAPI / Azure Search / etc.
        syms = payload.get("symbols", [])
        return AgentResult(
            summary=f"Collected market headlines for {len(syms)} symbols (stub).",
            details={
                "sources": ["stub"],
                "headlines": [],
            },
        )


# --------------------------------------------------------------------------------------
# Market Data Agent – yfinance-backed with NSE mapping and SSL fix
# --------------------------------------------------------------------------------------
class MarketDataAgent:
    def __init__(self, cfg: Dict[str, Any] | None = None):
        self.cfg = cfg or {}
        # yfinance config tweaks (optional)
        yf.shared._TRACE = False  # reduce noise

    def _fetch_history_one(
        self,
        yf_symbol: str,
        period: str = "2d",
        interval: str = "1d",
    ) -> List[Dict[str, Any]]:
        """
        Fetch history for one symbol using yfinance. Returns a list of OHLCV bars.
        """
        bars: List[Dict[str, Any]] = []
        try:
            # Using Ticker.history gives per-symbol DataFrame, easier to handle safely
            tkr = yf.Ticker(yf_symbol)
            df = tkr.history(period=period, interval=interval, auto_adjust=False)
            if df is None or df.empty:
                return bars

            # Normalize columns (yfinance uses capitalized names)
            for ts, row in df.iterrows():
                try:
                    bars.append({
                        "time": getattr(ts, "to_pydatetime", lambda: ts)().isoformat(),
                        "open": float(row.get("Open", row.get("open", math.nan))),
                        "high": float(row.get("High", row.get("high", math.nan))),
                        "low": float(row.get("Low", row.get("low", math.nan))),
                        "close": float(row.get("Close", row.get("close", math.nan))),
                        "volume": float(row.get("Volume", row.get("volume", 0.0))),
                    })
                except Exception:
                    # Skip malformed rows
                    continue
        except Exception as e:
            # Let caller aggregate these errors into details
            raise RuntimeError(f"{yf_symbol}: {e}")
        return bars

    def _compute_breadth(self, history_map: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
        """
        Compute a simple gainers/losers ratio from last two 'close' values per symbol.
        """
        gainers = losers = 0
        for sym, series in history_map.items():
            if len(series) < 2:
                continue
            c0 = series[-2].get("close")
            c1 = series[-1].get("close")
            if c0 is None or c1 is None:
                continue
            if c1 > c0:
                gainers += 1
            elif c1 < c0:
                losers += 1
        total = max(1, gainers + losers)
        return {
            "gainers": float(gainers),
            "losers": float(losers),
            "ratio": float(gainers) / float(total),
        }

    def run(self, payload: Dict[str, Any]) -> AgentResult:
        symbols: List[str] = payload.get("symbols", []) or []
        seg = payload.get("segment", "EQ")

        # Map to Yahoo symbols
        yahoo_map = {s: to_yahoo_symbol(s) for s in symbols}

        history: Dict[str, List[Dict[str, Any]]] = {}
        last_price: Dict[str, float] = {}
        errors: List[str] = []

        # Fetch each symbol separately for robust error handling
        for sym in symbols:
            ysym = yahoo_map.get(sym) or sym
            try:
                bars = self._fetch_history_one(ysym, period="2d", interval="1d")
                history[sym] = bars
                if bars:
                    last_price[sym] = float(bars[-1]["close"])
            except Exception as e:
                errors.append(str(e))
                history[sym] = []
                # leave last_price absent if failed

        # Gift Nifty premarket proxy:
        # Yahoo doesn't expose true GIFT pre-open; use NIFTY 50 as a proxy.
        gift_proxy_symbol = "^NSEI"
        gift_snapshot: Dict[str, Any] = {"proxy": gift_proxy_symbol, "note": "Using NIFTY 50 as proxy for GIFT premarket"}
        try:
            gift_bars = self._fetch_history_one(gift_proxy_symbol, period="2d", interval="1d")
            if gift_bars:
                gift_snapshot.update({
                    "last_close": gift_bars[-1]["close"],
                    "prev_close": gift_bars[-2]["close"] if len(gift_bars) > 1 else None,
                    "change_pct": (
                        (gift_bars[-1]["close"] - gift_bars[-2]["close"]) / gift_bars[-2]["close"] * 100.0
                        if len(gift_bars) > 1 and gift_bars[-2]["close"] else None
                    ),
                })
        except Exception as e:
            errors.append(f"GIFT proxy fetch error: {e}")

        breadth = self._compute_breadth(history)

        details = {
            "raw_market_data": {
                "history": history,        # per-symbol OHLCV
                "yahoo_map": yahoo_map,    # original -> yahoo symbol mapping
            },
            "last": last_price,            # per-symbol last close
            "breadth": breadth,            # gainers/losers ratio
            "premarket": {
                "gift_nifty": gift_snapshot
            },
            "errors": errors,              # collect any per-symbol errors for debugging
        }

        # Compose a human-friendly summary
        ok = sum(1 for s in symbols if history.get(s))
        failed = len(symbols) - ok
        summary = f"Fetched history for {ok}/{len(symbols)} symbols. Breadth g/l={int(breadth['gainers'])}/{int(breadth['losers'])} (ratio={breadth['ratio']:.2f})."
        if errors:
            summary += f" Errors: {min(3, len(errors))} shown; see details.errors."

        return AgentResult(summary=summary, details=details)
