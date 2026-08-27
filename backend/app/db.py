"""SQLite 持久化:每次对账是一个 run(上传的文件 + 解析结果 + 匹配结果)。

本地文件: backend/app/data/recon.db;上传文件: backend/app/data/uploads/<run_id>/
"""
from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .models import MatchItem, ParsedOrder


def _data_dir() -> Path:
    """数据目录:开发时在 app/data;打包成 exe 后放在 exe 同目录的 data 下(可移植、可备份)。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent / "data"


DATA_DIR = _data_dir()
DB_PATH = DATA_DIR / "recon.db"
UPLOAD_DIR = DATA_DIR / "uploads"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
    id TEXT PRIMARY KEY,
    created_at TEXT,
    channel_type TEXT,
    pms_type TEXT,
    channel_file TEXT,
    pms_file TEXT,
    stats_json TEXT
);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, side TEXT,
    order_no TEXT, channel TEXT, guest_name TEXT, room_type TEXT, nights INTEGER,
    check_in TEXT, check_out TEXT, order_amount REAL, commission_amount REAL,
    settle_amount REAL, status TEXT, book_time TEXT, remark TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS matches(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT, kind TEXT,
    channel_order_id INTEGER, pms_order_id INTEGER,
    diff_amount REAL, notes_json TEXT
);
CREATE TABLE IF NOT EXISTS mappings(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, side TEXT, parser_type TEXT,
    column_map TEXT, created_at TEXT, signature TEXT
);
CREATE TABLE IF NOT EXISTS plans(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    left_key TEXT, right_key TEXT,
    left_has_header INTEGER DEFAULT 1, right_has_header INTEGER DEFAULT 1,
    comparisons TEXT, created_at TEXT,
    tables TEXT
);
CREATE TABLE IF NOT EXISTS recon_runs(
    id TEXT PRIMARY KEY,
    plan_id INTEGER, created_at TEXT,
    left_file TEXT, right_file TEXT, result_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_orders_run ON orders(run_id);
CREATE INDEX IF NOT EXISTS idx_matches_run ON matches(run_id);
"""


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    try:
        conn.executescript(_SCHEMA)
        # 兼容旧库:补 signature 列(格式签名)与 plans 的 has_header 列
        cols = [r[1] for r in conn.execute("PRAGMA table_info(mappings)").fetchall()]
        if "signature" not in cols:
            conn.execute("ALTER TABLE mappings ADD COLUMN signature TEXT")
        pcols = [r[1] for r in conn.execute("PRAGMA table_info(plans)").fetchall()]
        if "left_has_header" not in pcols:
            conn.execute("ALTER TABLE plans ADD COLUMN left_has_header INTEGER DEFAULT 1")
            conn.execute("ALTER TABLE plans ADD COLUMN right_has_header INTEGER DEFAULT 1")
        if "tables" not in pcols:
            conn.execute("ALTER TABLE plans ADD COLUMN tables TEXT")
        conn.commit()
    finally:
        conn.close()


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6]


def create_run(channel_type: str, pms_type: str, channel_file: str, pms_file: str) -> str:
    run_id = _new_run_id()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO runs(id, created_at, channel_type, pms_type, channel_file, pms_file, stats_json) "
            "VALUES(?,?,?,?,?,?,?)",
            (run_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), channel_type, pms_type,
             channel_file, pms_file, "{}"))
        conn.commit()
    finally:
        conn.close()
    return run_id


def update_run_stats(run_id: str, stats: dict):
    conn = _conn()
    try:
        conn.execute("UPDATE runs SET stats_json=? WHERE id=?", (json.dumps(stats, ensure_ascii=False), run_id))
        conn.commit()
    finally:
        conn.close()


def delete_run(run_id: str):
    conn = _conn()
    try:
        conn.execute("DELETE FROM matches WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM orders WHERE run_id=?", (run_id,))
        conn.execute("DELETE FROM runs WHERE id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------- 订单 ----------------

def save_orders(run_id: str, side: str, orders: list):
    conn = _conn()
    try:
        for o in orders:
            cur = conn.execute(
                "INSERT INTO orders(run_id, side, order_no, channel, guest_name, room_type, nights, "
                "check_in, check_out, order_amount, commission_amount, settle_amount, status, "
                "book_time, remark, raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, side, o.order_no, o.channel, o.guest_name, o.room_type, o.nights,
                 o.check_in, o.check_out, o.order_amount, o.commission_amount, o.settle_amount,
                 o.status, o.book_time, o.remark,
                 json.dumps(o.raw, ensure_ascii=False, default=str)))
            o.id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()


def _row_to_order(r: sqlite3.Row) -> ParsedOrder:
    o = ParsedOrder(
        order_no=r["order_no"], channel=r["channel"], guest_name=r["guest_name"],
        room_type=r["room_type"], nights=r["nights"], check_in=r["check_in"],
        check_out=r["check_out"], order_amount=r["order_amount"],
        commission_amount=r["commission_amount"], settle_amount=r["settle_amount"],
        status=r["status"], book_time=r["book_time"], remark=r["remark"],
        id=r["id"])
    try:
        o.raw = json.loads(r["raw_json"] or "{}")
    except ValueError:
        o.raw = {}
    return o


def load_orders(run_id: str, side: str) -> list:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE run_id=? AND side=? ORDER BY id", (run_id, side)).fetchall()
        return [_row_to_order(r) for r in rows]
    finally:
        conn.close()


# ---------------- 匹配结果 ----------------

def save_matches(run_id: str, items: list):
    conn = _conn()
    try:
        for it in items:
            co_id = (it.channel_order or {}).get("id")
            po_id = (it.pms_order or {}).get("id")
            conn.execute(
                "INSERT INTO matches(run_id, kind, channel_order_id, pms_order_id, diff_amount, notes_json) "
                "VALUES(?,?,?,?,?,?)",
                (run_id, it.kind, co_id, po_id, it.diff_amount,
                 json.dumps(it.notes, ensure_ascii=False)))
        conn.commit()
    finally:
        conn.close()


def delete_matches(run_id: str):
    conn = _conn()
    try:
        conn.execute("DELETE FROM matches WHERE run_id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()


def load_run_data(run_id: str):
    """返回 (run_row|None, channel_orders, pms_orders, match_items)。"""
    conn = _conn()
    try:
        run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if run is None:
            return None, [], [], []
        ch = [_row_to_order(r) for r in
              conn.execute("SELECT * FROM orders WHERE run_id=? AND side='channel' ORDER BY id", (run_id,))]
        pm = [_row_to_order(r) for r in
              conn.execute("SELECT * FROM orders WHERE run_id=? AND side='pms' ORDER BY id", (run_id,))]
        items = []
        for r in conn.execute("SELECT * FROM matches WHERE run_id=? ORDER BY id", (run_id,)):
            co = next((o.to_dict() for o in ch if o.id == r["channel_order_id"]), None)
            po = next((o.to_dict() for o in pm if o.id == r["pms_order_id"]), None)
            try:
                notes = json.loads(r["notes_json"] or "[]")
            except ValueError:
                notes = []
            items.append(MatchItem(kind=r["kind"], channel_order=co, pms_order=po,
                                   diff_amount=r["diff_amount"], notes=notes))
        return run, ch, pm, items
    finally:
        conn.close()


# ---------------- 字段映射预设 ----------------

def save_mapping(name: str, side: str, parser_type: str, column_map: dict,
                 signature: str = None) -> int:
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO mappings(name, side, parser_type, column_map, created_at, signature) "
            "VALUES(?,?,?,?,?,?)",
            (name, side, parser_type, json.dumps(column_map, ensure_ascii=False),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S"), signature))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def find_mapping_by_signature(side: str, signature: str):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM mappings WHERE side=? AND signature=? ORDER BY id DESC LIMIT 1",
            (side, signature)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_mappings(side: str = None, parser_type: str = None) -> list:
    conn = _conn()
    try:
        sql = "SELECT * FROM mappings"
        conds, params = [], []
        if side:
            conds.append("side=?")
            params.append(side)
        if parser_type:
            conds.append("parser_type=?")
            params.append(parser_type)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY id DESC"
        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            try:
                cm = json.loads(r["column_map"] or "{}")
            except ValueError:
                cm = {}
            out.append({"id": r["id"], "name": r["name"], "side": r["side"],
                        "parser_type": r["parser_type"], "column_map": cm,
                        "created_at": r["created_at"], "signature": r["signature"]})
        return out
    finally:
        conn.close()


def delete_mapping(mid: int):
    conn = _conn()
    try:
        conn.execute("DELETE FROM mappings WHERE id=?", (mid,))
        conn.commit()
    finally:
        conn.close()


def update_mapping(mid: int, name: str, column_map: dict):
    conn = _conn()
    try:
        conn.execute("UPDATE mappings SET name=?, column_map=? WHERE id=?",
                     (name, json.dumps(column_map, ensure_ascii=False), mid))
        conn.commit()
    finally:
        conn.close()


# ---------------- 对账方案(通用对账工具) ----------------

def save_plan(name: str, tables: list) -> int:
    """保存对账方案。tables: [{name, key, has_header, comparisons}] 表一为主表。"""
    conn = _conn()
    try:
        cur = conn.execute(
            "INSERT INTO plans(name, tables, created_at) VALUES(?,?,?)",
            (name, json.dumps(tables, ensure_ascii=False),
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_plan(pid: int, name: str, tables: list):
    conn = _conn()
    try:
        conn.execute("UPDATE plans SET name=?, tables=? WHERE id=?",
                     (name, json.dumps(tables, ensure_ascii=False), pid))
        conn.commit()
    finally:
        conn.close()


def _plan_to_dict(row) -> dict:
    d = dict(row)
    if d.get("tables"):
        try:
            d["tables"] = json.loads(d["tables"])
            return d
        except ValueError:
            pass
    # 旧结构兜底:由 left_key/right_key/comparisons 组装成两张表
    try:
        comps = json.loads(d.get("comparisons") or "[]")
    except ValueError:
        comps = []
    d["tables"] = [
        {"name": "表一", "key": d.get("left_key") or "A",
         "has_header": bool(d.get("left_has_header", 1)), "comparisons": []},
        {"name": "表二", "key": d.get("right_key") or "B",
         "has_header": bool(d.get("right_has_header", 1)), "comparisons": comps},
    ]
    return d


def get_plan(pid: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (pid,)).fetchone()
        return _plan_to_dict(row) if row else None
    finally:
        conn.close()


def list_plans() -> list:
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM plans ORDER BY id DESC").fetchall()
        return [_plan_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_plan(pid: int):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM plans WHERE id=?", (pid,)).fetchone()
        return _plan_to_dict(row) if row else None
    finally:
        conn.close()


def list_plans() -> list:
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM plans ORDER BY id DESC").fetchall()
        return [_plan_to_dict(r) for r in rows]
    finally:
        conn.close()


def delete_plan(pid: int):
    conn = _conn()
    try:
        conn.execute("DELETE FROM plans WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()


def save_recon_run(run_id: str, plan_id: int, left_file: str, right_file: str, result: dict):
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO recon_runs(id, plan_id, created_at, left_file, right_file, result_json) "
            "VALUES(?,?,?,?,?,?)",
            (run_id, plan_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             left_file, right_file, json.dumps(result, ensure_ascii=False, default=str)))
        conn.commit()
    finally:
        conn.close()


def get_recon_run(run_id: str):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM recon_runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["result"] = json.loads(d.get("result_json") or "{}")
        except ValueError:
            d["result"] = {}
        return d
    finally:
        conn.close()
