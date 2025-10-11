from __future__ import annotations
import argparse, csv, json
from .db import DB
from .utils import load_app_config

def export_table(table: str, out_file: str, limit: int = 10000):
    cfg = load_app_config()
    db = DB(cfg)
    if table == "orders":
        rows = db.fetch_orders(limit)
    elif table == "equity":
        rows = db.fetch_equity(limit)
    elif table == "positions":
        rows = db.fetch_positions_latest()
    elif table == "logs":
        rows = db.fetch_logs(limit)
    else:
        raise SystemExit(f"Unknown table: {table}")

    if not rows:
        print("No data")
        return

    # normalize JSON columns to text
    for r in rows:
        for k,v in list(r.items()):
            if isinstance(v, (dict, list)):
                r[k] = json.dumps(v)

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Exported {len(rows)} rows from {table} -> {out_file}")

def main():
    p = argparse.ArgumentParser("Export ledger to CSV")
    p.add_argument("--table", required=True, choices=["orders","equity","positions","logs"])
    p.add_argument("--out", required=True, help="Output CSV path")
    p.add_argument("--limit", type=int, default=10000)
    a = p.parse_args()
    export_table(a.table, a.out, a.limit)

if __name__ == "__main__":
    main()
