from __future__ import annotations
from typing import Dict, Any
import time, hashlib, random

def make_coid(order: Dict[str, Any]) -> str:
    # deterministic-ish client order id; include minute bucket to allow repeated trades later
    base = f"{order.get('symbol')}|{order.get('side')}|{order.get('qty')}|{int(float(order.get('price',0))*100)}|{int(time.time()//60)}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]

def place_with_retry(broker, state: Dict[str, Any], order: Dict[str, Any], max_retries: int = 3, backoff: float = 0.25) -> Dict[str, Any]:
    coid = make_coid(order)
    idx = state.setdefault("order_index", {})
    if coid in idx:
        return {"status": "duplicate_skipped", "coid": coid}
    # Retry loop
    attempt = 0; last = {}
    while attempt < max_retries:
        try:
            resp = broker.place_market(order)
            last = resp or {}
            status = last.get("status","")
            if status and status not in ("error","blocked","failed"):
                idx[coid] = 1
                return {"status": status, "coid": coid, "resp": last}
        except Exception as e:
            last = {"status":"exception","error":str(e)}
        time.sleep(backoff * (2**attempt) + random.uniform(0, backoff/5))
        attempt += 1
    return {"status": "failed", "coid": coid, "resp": last}
