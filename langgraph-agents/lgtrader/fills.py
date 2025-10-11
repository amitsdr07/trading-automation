from __future__ import annotations
from typing import Dict, Any, List
from .utils import now_ist
from .metrics import apply_fill

def reconcile_orders(state: Dict[str, Any]) -> None:
    cfg = state.get("cfg", {}) or {}
    live = bool((cfg.get("broker") or {}).get("live_trading", False))
    if not live: 
        return
    broker_name = (cfg.get("broker") or {}).get("broker", "paper").lower()
    # get broker adapter
    try:
        if broker_name == "zerodha":
            from .brokers.zerodha import ZerodhaBroker as B
        elif broker_name == "angel":
            from .brokers.angel import AngelBroker as B
        else:
            return
        b = B(cfg)
    except Exception:
        return
    # poll order book and mark fills
    try:
        ob = b.list_orders()
    except Exception:
        ob = []
    idx = {o.get("id") or o.get("order_id") or o.get("broker_order_id"): o for o in (state.get("orders") or [])}
    filled_ids = set()
    for rec in ob:
        oid = rec.get("order_id") or rec.get("id") or rec.get("broker_order_id")
        status = (rec.get("status") or "").upper()
        if not oid or status != "COMPLETE":
            continue
        filled_ids.add(oid)
        # find our local order object to fill
        for o in state.get("orders", []):
            if o.get("broker_order_id") == oid or o.get("id") == oid:
                if o.get("_filled"): 
                    continue
                o["_filled"] = True
                o["status"] = "FILLED"
                # use avg_price from broker or fallback to our price
                px = float(rec.get("average_price") or rec.get("avg_price") or rec.get("price") or o.get("price"))
                qty = int(rec.get("filled_quantity") or rec.get("quantity") or o.get("qty", 0))
                fill = {"symbol": o["symbol"], "side": o["side"], "qty": qty, "price": px, "meta": o.get("meta",{})}
                apply_fill(state, fill)
    # clear pending orders that are filled
    po = []
    for p in state.get("pending_orders", []):
        if p.get("broker_order_id") not in filled_ids:
            po.append(p)
    state["pending_orders"] = po
