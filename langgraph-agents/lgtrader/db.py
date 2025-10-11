from __future__ import annotations
from typing import Dict, Any, List, Tuple
import sqlite3, json, os
from contextlib import contextmanager

try:
    import psycopg2  # type: ignore
    HAS_PG = True
except Exception:
    HAS_PG = False

def _cfg_db(cfg: Dict[str, Any]) -> Dict[str, Any]:
    d = (cfg or {}).get("db") or {}
    kind = (d.get("kind") or "sqlite").lower()
    if kind not in ("sqlite","postgres"): kind = "sqlite"
    path = d.get("path") or "trader.db"
    dsn = d.get("dsn") or ""
    schema = d.get("schema") or "public"
    return {"kind": kind, "path": path, "dsn": dsn, "schema": schema}

class DB:
    def __init__(self, cfg: Dict[str, Any]):
        c = _cfg_db(cfg)
        self.kind = c["kind"]
        self.path = c["path"]
        self.dsn = c["dsn"]
        self.schema = c["schema"]
        if self.kind == "postgres" and not HAS_PG:
            self.kind = "sqlite"  # fallback
        self._ensure_schema()

    @contextmanager
    def _conn(self):
        if self.kind == "sqlite":
            conn = sqlite3.connect(self.path)
            try:
                yield conn
            finally:
                conn.commit()
                conn.close()
        else:
            import psycopg2
            conn = psycopg2.connect(self.dsn)
            try:
                yield conn
            finally:
                conn.commit()
                conn.close()

    def _ensure_schema(self):
        with self._conn() as cn:
            cur = cn.cursor()
            if self.kind == "postgres":
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema};")
                prefix = f"{self.schema}."
            else:
                prefix = ""
            cur.execute(f"CREATE TABLE IF NOT EXISTS {prefix}orders (\n id INTEGER PRIMARY KEY AUTOINCREMENT,\n ts TEXT, symbol TEXT, side TEXT, qty INTEGER, price REAL, status TEXT, strategy TEXT, meta TEXT\n);")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {prefix}equity (\n id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, equity REAL\n);")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {prefix}positions (\n id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, symbol TEXT, side TEXT, qty INTEGER, avg_price REAL\n);")
            cur.execute(f"CREATE TABLE IF NOT EXISTS {prefix}logs (\n id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, data TEXT\n);")

    def insert_order(self, ts: str, order: Dict[str, Any]):
        with self._conn() as cn:
            cur = cn.cursor()
            strategy = (order.get("meta") or {}).get("strategy","")
            meta = json.dumps(order.get("meta") or {})
            cur.execute(f"INSERT INTO {'%s'% (self.schema + '.' if self.kind=='postgres' else '')}orders (ts,symbol,side,qty,price,status,strategy,meta) VALUES (?,?,?,?,?,?,?,?)" if self.kind=='sqlite' else f"INSERT INTO {self.schema}.orders (ts,symbol,side,qty,price,status,strategy,meta) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (ts, order.get("symbol"), order.get("side"), int(order.get("qty",0)), float(order.get("price",0.0)), order.get("status",""), strategy, meta))

    def insert_equity(self, ts: str, equity: float):
        with self._conn() as cn:
            cur = cn.cursor()
            cur.execute(f"INSERT INTO {'%s'% (self.schema + '.' if self.kind=='postgres' else '')}equity (ts,equity) VALUES (?,?)" if self.kind=='sqlite' else f"INSERT INTO {self.schema}.equity (ts,equity) VALUES (%s,%s)", (ts, float(equity)))

    def upsert_positions_snapshot(self, ts: str, positions: Dict[str, Any]):
        with self._conn() as cn:
            cur = cn.cursor()
            # simple snapshot insert (no dedup)
            for sym, pos in (positions or {}).items():
                cur.execute(f"INSERT INTO {'%s'% (self.schema + '.' if self.kind=='postgres' else '')}positions (ts,symbol,side,qty,avg_price) VALUES (?,?,?,?,?)" if self.kind=='sqlite' else f"INSERT INTO {self.schema}.positions (ts,symbol,side,qty,avg_price) VALUES (%s,%s,%s,%s,%s)", (ts, sym, pos.get("side"), int(pos.get("qty",0)), float(pos.get("avg_price",0.0))))

    def insert_log(self, ts: str, data: Dict[str, Any]):
        with self._conn() as cn:
            cur = cn.cursor()
            cur.execute(f"INSERT INTO {'%s'% (self.schema + '.' if self.kind=='postgres' else '')}logs (ts,data) VALUES (?,?)" if self.kind=='sqlite' else f"INSERT INTO {self.schema}.logs (ts,data) VALUES (%s,%s)", (ts, json.dumps(data)))

    def fetch_orders(self, limit: int = 500):
        with self._conn() as cn:
            cur = cn.cursor()
            table = f"{self.schema}.orders" if self.kind=='postgres' else "orders"
            q = f"SELECT ts,symbol,side,qty,price,status,strategy,meta FROM {table} ORDER BY id DESC LIMIT ?"
            params = (limit,)
            if self.kind == 'postgres':
                q = q.replace(" LIMIT ?", " LIMIT %s")
            cur.execute(q, params)
            cols = ["ts","symbol","side","qty","price","status","strategy","meta"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def fetch_equity(self, limit: int = 1000):
        with self._conn() as cn:
            cur = cn.cursor()
            table = f"{self.schema}.equity" if self.kind=='postgres' else "equity"
            q = f"SELECT ts,equity FROM {table} ORDER BY id ASC LIMIT ?"
            params = (limit,)
            if self.kind == 'postgres':
                q = q.replace(" LIMIT ?", " LIMIT %s")
            cur.execute(q, params)
            cols = ["ts","equity"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def fetch_positions_latest(self):
        # naive: fetch the latest timestamp and return all rows for that ts
        with self._conn() as cn:
            cur = cn.cursor()
            table = f"{self.schema}.positions" if self.kind=='postgres' else "positions"
            cur.execute(f"SELECT MAX(ts) FROM {table}")
            row = cur.fetchone()
            if not row or not row[0]:
                return []
            ts = row[0]
            cur.execute(f"SELECT ts,symbol,side,qty,avg_price FROM {table} WHERE ts = %s" if self.kind=='postgres' else f"SELECT ts,symbol,side,qty,avg_price FROM {table} WHERE ts = ?", (ts,))
            cols = ["ts","symbol","side","qty","avg_price"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def fetch_logs(self, limit: int = 500):
        with self._conn() as cn:
            cur = cn.cursor()
            table = f"{self.schema}.logs" if self.kind=='postgres' else "logs"
            q = f"SELECT ts,data FROM {table} ORDER BY id DESC LIMIT ?"
            params = (limit,)
            if self.kind == 'postgres':
                q = q.replace(" LIMIT ?", " LIMIT %s")
            cur.execute(q, params)
            cols = ["ts","data"]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
