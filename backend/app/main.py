"""FastAPI 入口:本地部署,单机使用。表对比工具(映射/方案驱动,列按 Excel 位置)。

启动: python -m app.main  ->  http://127.0.0.1:8000(被占用自动换端口)
API:
  POST /api/preview              上传文件,返回表头 + 样例行 + 建议主键/对比列(列字母)
  GET/POST /api/plans            对账方案(映射)查询/新建
  PUT/DELETE /api/plans/{id}     对账方案 更新/删除
  POST /api/recon                选方案 + 上传多个文件(表一/表二/...) -> 执行多表对账
  GET  /api/export/{run_id}      导出差异报表 CSV
"""
from __future__ import annotations

import csv
import io
import json
import shutil
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import db
from .engine import (_to_number, build_rows, col_index, col_letter,
                     column_stats, format_value, read_table, run_recon_multi,
                     stats)
from .parsers.base import _norm_header
from .parsers.channel import ChannelParser

BASE_DIR = Path(__file__).resolve().parent

TABLE_CN = ["一", "二", "三", "四", "五", "六"]
MAX_TABLES = 6


def _static_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller 打包后
        return Path(sys._MEIPASS) / "app" / "static"
    return BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="表对比工具", version="0.6.0", lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "table-diff", "version": "0.6.0"}


def _to_bool(v) -> int:
    return 1 if str(v or "").lower() in ("1", "true", "on", "yes") else 0


def _check_letter(value, field: str):
    if col_index(value) is None:
        raise HTTPException(status_code=400,
                            detail=f"{field}列写法不对:「{value}」,应类似 A / B / C")


# ---------------- 预览 / 建议 ----------------

def _suggest(headers, rows):
    """根据内置别名与列内容,建议主键列与对比列(返回 Excel 列字母)。"""
    norm_map = {}
    for canon, aliases in ChannelParser().COLUMN_ALIASES.items():
        for a in aliases:
            norm_map[_norm_header(a)] = canon
    key_pos = None
    for i, h in enumerate(headers):
        if norm_map.get(_norm_header(h)) == "order_no":
            key_pos = i
            break
    num_pos = []
    for i, h in enumerate(headers):
        vals = [row[i] for row in rows[:50] if i < len(row) and str(row[i]).strip()]
        if len(vals) >= 2:
            ns = [_to_number(v) for v in vals]
            if sum(1 for x in ns if x is not None) / len(vals) >= 0.9:
                num_pos.append(i)
    return (col_letter(key_pos) if key_pos is not None else None,
            [col_letter(i) for i in num_pos[:4]])


@app.post("/api/preview")
async def preview(file: UploadFile = File(...), has_header: str = Form("1")):
    """上传文件,返回表头 + 样例行 + 建议主键/对比列(Excel 列字母)。"""
    tmp_dir = db.UPLOAD_DIR / "preview"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp = tmp_dir / (uuid.uuid4().hex[:8] + Path(file.filename).suffix)
    tmp.write_bytes(await file.read())
    try:
        headers, rows = read_table(tmp)
        hh = _to_bool(has_header)
        key, compares = _suggest(headers, rows) if hh else (None, [])
        labels = ([f"{col_letter(i)}({h})" for i, h in enumerate(headers)]
                  if hh else [f"列{col_letter(i)}" for i in range(len(headers))])
        return {"headers": headers, "labels": labels,
                "samples": rows[:5],
                "suggested_key": key, "suggested_compare": compares}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp.unlink(missing_ok=True)


# ---------------- 对账方案(映射) CRUD ----------------

def _parse_tables(s: str) -> list:
    try:
        tables = json.loads(s)
    except ValueError:
        raise HTTPException(status_code=400, detail="tables 不是合法 JSON")
    if not isinstance(tables, list) or not tables:
        raise HTTPException(status_code=400, detail="tables 必须是非空数组")
    if len(tables) < 2:
        raise HTTPException(status_code=400, detail="至少需要两张表(表一 + 一张对比表)")
    if len(tables) > MAX_TABLES:
        raise HTTPException(status_code=400, detail=f"最多 {MAX_TABLES} 张表")

    out = []
    for i, t in enumerate(tables):
        if not isinstance(t, dict) or not str(t.get("name") or "").strip():
            raise HTTPException(status_code=400, detail=f"表{TABLE_CN[i]}缺少表名")
        _check_letter(t.get("key"), f"表{TABLE_CN[i]}主键")
        comps = []
        for c in (t.get("comparisons") or []):
            if not isinstance(c, dict):
                raise HTTPException(status_code=400, detail="对比字段需是对象")
            _check_letter(c.get("left"), "对比左")
            _check_letter(c.get("right"), "对比右")
            comps.append({"left": str(c["left"]).upper(), "right": str(c["right"]).upper(),
                          "tolerance": c.get("tolerance")})
        out.append({
            "name": str(t["name"]).strip(),
            "key": str(t["key"]).upper(),
            "has_header": _to_bool(t.get("has_header", "1")),
            "comparisons": comps,
        })
    out[0]["comparisons"] = []  # 表一为主表,无对比列
    return out


@app.get("/api/plans")
def list_plans():
    return {"plans": db.list_plans()}


@app.post("/api/plans")
def create_plan(name: str = Form(...), tables: str = Form(...)):
    if not name.strip():
        raise HTTPException(status_code=400, detail="请填写方案名称")
    tbs = _parse_tables(tables)
    pid = db.save_plan(name.strip(), tbs)
    return {"id": pid}


@app.put("/api/plans/{pid}")
def update_plan_route(pid: int, name: str = Form(...), tables: str = Form(...)):
    if db.get_plan(pid) is None:
        raise HTTPException(status_code=404, detail="方案不存在")
    tbs = _parse_tables(tables)
    db.update_plan(pid, name.strip(), tbs)
    return {"ok": True}


@app.delete("/api/plans/{pid}")
def delete_plan_route(pid: int):
    db.delete_plan(pid)
    return {"ok": True}


# ---------------- 执行对账 ----------------

def _explain(kind: str, master: str, sat: str) -> str:
    if kind == "diff":
        return "数值不一致"
    if kind == "matched":
        return "对比列全部一致"
    if kind == "master_only":
        return f"「{master}」有,「{sat}」无"
    return f"「{sat}」有,「{master}」无"


def _build_export_csv(result: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    tables = result.get("tables") or [{}]
    master = tables[0].get("name", "表一")
    sat_names = [t.get("name") for t in tables[1:] if t.get("name")]
    sat_label = "、".join(sat_names) if sat_names else "表二"
    # 按对比表分组,每组表头: 主键 + 表名·列名 对 + 说明
    by_table: dict = {}
    for it in result.get("items", []):
        by_table.setdefault(it.get("table", ""), []).append(it)
    for sat, items in by_table.items():
        w.writerow([f"与【{sat}】对比"])
        cols = (items[0].get("cols") or []) if items else []
        header = ["主键"]
        for c in cols:
            header.append(f"{master}·{c['left']}")
        for c in cols:
            header.append(f"{sat}·{c['right']}")
        header.append("说明")
        w.writerow(header)
        for it in items:
            row = [it["key"]]
            row += [format_value(c.get("left_val")) for c in (it.get("cols") or [])]
            row += [format_value(c.get("right_val")) for c in (it.get("cols") or [])]
            row.append(_explain(it["kind"], master, sat))
            w.writerow(row)
    s = result.get("stats", {})
    col_stats = result.get("col_stats", [])
    if col_stats:
        w.writerow([])
        w.writerow(["列差异统计(按对比列)"])
        w.writerow(["对比表", "表一列", "对比表列", "差异条数", "差异合计"])
        for cs in col_stats:
            w.writerow([cs.get("table", ""), cs.get("left", ""), cs.get("right", ""),
                        cs.get("count", 0), f"{cs.get('amount', 0.0):.2f}"])
    w.writerow([])
    w.writerow([f"统计: 一致 {s.get('matched', 0)} 条 | 有差异 {s.get('diff', 0)} 条 | "
                f"「{master}」独有 {s.get('master_only', 0)} 条 | 「{sat_label}」独有 {s.get('table_only', 0)} 条 | "
                f"差异合计 {s.get('diff_amount', 0.0):.2f}"])
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


@app.post("/api/recon")
async def recon(plan_id: int = Form(...),
                files: List[UploadFile] = File(...)):
    plan = db.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="对账方案不存在")
    tables = plan["tables"]
    if len(files) != len(tables):
        raise HTTPException(
            status_code=400,
            detail=f"需要上传 {len(tables)} 个文件,依次对应: {'、'.join(t['name'] for t in tables)};实际收到 {len(files)} 个")

    run_id = uuid.uuid4().hex[:12]
    save_dir = db.UPLOAD_DIR / run_id
    save_dir.mkdir(parents=True, exist_ok=True)
    table_data = []
    try:
        for i, (t, f) in enumerate(zip(tables, files)):
            path = save_dir / (f"table{i + 1}_" + Path(f.filename).name)
            path.write_bytes(await f.read())
            headers, rows = read_table(path)
            data, labels = build_rows(headers, rows, bool(t.get("has_header", 1)))
            table_data.append({"name": t["name"], "data": data, "labels": labels,
                               "key": t["key"], "comparisons": t.get("comparisons", [])})
        master = table_data[0]
        items = run_recon_multi(master["data"], master["labels"], master["key"],
                                table_data[1:])
    except ValueError as e:
        shutil.rmtree(save_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))

    result = {
        "plan_name": plan["name"],
        "tables": [{"name": td["name"], "labels": td["labels"]} for td in table_data],
        "stats": stats(items),
        "col_stats": column_stats(items),
        "items": [it.to_dict() for it in items],
    }
    db.save_recon_run(run_id, plan_id,
                      ", ".join(f.filename for f in files),
                      "", result)
    return {"run_id": run_id, **result}


@app.get("/api/export/{run_id}")
def export(run_id: str):
    run = db.get_recon_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="对账结果不存在")
    data = _build_export_csv(run["result"])
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="table_diff_{run_id}.csv"'},
    )


# 静态前端(放在最后挂载,API 路由优先)
app.mount("/", StaticFiles(directory=_static_dir(), html=True), name="static")


def run_server():
    """启动本地服务:默认 8000,被占用自动回退到备用端口(打印实际地址)。"""
    import os
    import socket

    candidates = [int(os.environ.get("TABLE_DIFF_PORT", "8000")), 8765, 8080, 9000]
    chosen = None
    for p in dict.fromkeys(candidates):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
            chosen = p
            break
        except OSError:
            continue
    if chosen is None:
        print("[错误] 没有可用端口,请设置环境变量 HOTEL_RECON_PORT 指定端口")
        raise SystemExit(1)
    if chosen != candidates[0]:
        print(f"[提示] 端口 {candidates[0]} 被占用,已改用端口 {chosen}")
    print(f"[提示] 请用浏览器打开 http://127.0.0.1:{chosen}")
    uvicorn.run(app, host="127.0.0.1", port=chosen)


if __name__ == "__main__":
    run_server()
