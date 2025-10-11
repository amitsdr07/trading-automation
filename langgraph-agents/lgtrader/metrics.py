from __future__ import annotations
from typing import Dict, Any
from .utils import now_ist
from .db import DB

def init_finance(state: Dict[str, Any]) -> None:
    cash = float(state.get("global_capital") or state.get("cfg",{}).get("capital") or 0.0)
    state["cash"] = cash
    state["equity"] = cash
    state["equity_curve"] = []
    state["peak_equity"] = cash
    state["max_drawdown"] = 0.0
    state["realized_pnl"] = 0.0
    state["unrealized_pnl"] = 0.0

def _position_value(pos: Dict[str, Any], ltp: float) -> float:
    side = pos.get("side"); qty = int(pos.get("qty", 0)); avg = float(pos.get("avg_price", 0.0))
    if qty <= 0: return 0.0
    if side == "BUY":
        return ltp * qty
    else:  # short
        return (2*avg - ltp) * qty  # synthetic valuation for short; not used if you disallow shorts

def revalue_equity(state: Dict[str, Any]) -> None:
    # Compute unrealized pnl from positions using last_price map
    unreal = 0.0
    for sym, pos in (state.get("positions") or {}).items():
        ltp = float((state.get("last_price") or {}).get(sym, pos.get("avg_price", 0.0)))
        side = pos.get("side"); qty = int(pos.get("qty", 0)); avg = float(pos.get("avg_price", 0.0))
        if qty <= 0: continue
        if side == "BUY":
            unreal += (ltp - avg) * qty
        else:
            unreal += (avg - ltp) * qty
    state["unrealized_pnl"] = unreal
    state["equity"] = float(state.get("cash", 0.0)) + unreal
    # Drawdown tracking
    if state["equity"] > state.get("peak_equity", 0.0):
        state["peak_equity"] = state["equity"]
    dd = state.get("peak_equity", 0.0) - state["equity"]
    if dd > state.get("max_drawdown", 0.0):
        state["max_drawdown"] = dd
    # Append to equity curve (thin sampling)
    ec = state.setdefault("equity_curve", [])
    if not ec or (len(ec) % 10 == 0):
        ts = now_ist().isoformat()
        point = {"t": ts, "equity": state["equity"]}
        ec.append(point)
        try:
            DB(state.get("cfg", {})).insert_equity(ts, state["equity"])
        except Exception:
            pass

def apply_fill(state: Dict[str, Any], order: Dict[str, Any]) -> None:
    """Adjust cash/positions and realized PnL when an order is accepted."""
    sym = order["symbol"]; side = order["side"]; qty = int(order["qty"]); px = float(order["price"])
    pos = (state["positions"] or {}).get(sym)
    if not pos:
        # Opening new position
        meta = order.get("meta",{})
        sl = float(meta.get("sl", px)); tp = float(meta.get("tp", px))
        new_pos = {"symbol": sym, "side": side, "qty": qty, "avg_price": px, "stop_loss": sl, "target": tp, "strategy": meta.get("strategy","")}
        state["positions"][sym] = new_pos
        if side == "BUY":
            state["cash"] -= qty * px
        else:
            state["cash"] += qty * px  # short sale proceeds
    else:
        # If opposite side, assume full close for simplicity
        if pos.get("side") != side:
            # Close
            if pos["side"] == "BUY":
                state["cash"] += qty * px
                state["realized_pnl"] += (px - pos["avg_price"]) * qty
            else:
                state["cash"] -= qty * px
                state["realized_pnl"] += (pos["avg_price"] - px) * qty
            pos["qty"] -= qty
            if pos["qty"] <= 0:
                state["positions"].pop(sym, None)
        else:
            # Same-side add (average)
            tot_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["avg_price"]*pos["qty"] + px*qty) / max(tot_qty,1)
            pos["qty"] = tot_qty
            if side == "BUY":
                state["cash"] -= qty * px
            else:
                state["cash"] += qty * px
    # Update last price and equity
    state["last_price"][sym] = px
    revalue_equity(state)
