"""通用对账引擎:任意两个表格文件,按主键列(Excel 列位置)匹配,按配置的对比列逐项对比。

对账方案(映射)模型 —— 列用 Excel 字母 A/B/C/D... 表示所在列位置:
- left_key / right_key: 左右文件的主键列(如 left_key="A", right_key="C")
- comparisons: [{left, right, tolerance}] 对比列对(如 {"left":"D","right":"E"})
- 每侧可选:首行是否为表头(has_header)

输出四类: matched(一致) / diff(有差异) / left_only(仅左侧有) / right_only(仅右侧有)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .parsers.base import BaseParser, parse_date

DEFAULT_TOLERANCE = 0.01  # 数字对比默认容差(分)


# ---------------- 列位置(Excel 字母) ----------------

def col_letter(i: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA。"""
    s = ""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def col_index(letter) -> int:
    """'A' -> 0, 'B' -> 1, 'AA' -> 26;非法返回 None。"""
    s = str(letter or "").upper().strip()
    if not s or not re.fullmatch(r"[A-Z]{1,2}", s):
        return None
    n = 0
    for ch in s:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


# ---------------- 值归一化 ----------------

def _to_number(v) -> Optional[float]:
    if v is None:
        return None
    s = str(v).replace("¥", "").replace("￥", "").replace(",", "").replace("元", "").replace(" ", "").strip()
    if s.endswith("%"):
        s = s[:-1]
    if not s or s in ("-", "—", "/", "null", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_text(v) -> str:
    return re.sub(r"\s+", "", str(v or "")).strip().lower()


def norm_key(v) -> str:
    """主键归一化:'1001' / 1001 / '1001.0' 视为同一键;日期统一格式;文本去空白小写。"""
    n = _to_number(v)
    if n is not None:
        return f"{n:g}"
    d = parse_date(v)
    if d:
        return d
    return _norm_text(v)


def values_equal(a, b, tolerance: Optional[float]) -> bool:
    an, bn = _to_number(a), _to_number(b)
    if an is not None and bn is not None:
        return abs(an - bn) <= (tolerance if tolerance is not None else DEFAULT_TOLERANCE)
    return _norm_text(a) == _norm_text(b)


def format_value(v) -> str:
    n = _to_number(v)
    if n is not None:
        return f"{n:g}"
    return str(v if v is not None else "")


# ---------------- 文件读取 ----------------

def read_table(path):
    """读取表格(CSV/XLSX,自动编码),返回 (表头list, 数据行list)。"""
    return BaseParser().read_table(path)


def build_rows(headers, rows, has_header: bool):
    """按是否含表头构建数据行与列显示名。

    has_header=True : 首行是表头,列显示名用表头文本(如 '订单号')
    has_header=False: 首行也是数据,列显示名用 '列A' '列B'...
    """
    if has_header:
        return rows, [str(h) for h in headers]
    return [headers] + rows, [f"列{col_letter(i)}" for i in range(len(headers))]


def load_rows(path, has_header: bool):
    headers, rows = read_table(path)
    return build_rows(headers, rows, has_header)


# ---------------- 对账 ----------------

@dataclass
class ReconItem:
    kind: str                      # matched / diff / master_only / table_only
    key: str = ""
    cols: list = field(default_factory=list)  # [{left, right, left_val, right_val, equal}]
    table: str = ""                # 所属对比表名(映射定义,如 PMS流水/美团账单)

    def to_dict(self):
        return {"kind": self.kind, "key": self.key, "cols": self.cols, "table": self.table}


def _cell(row, pos) -> str:
    return row[pos] if pos < len(row) else ""


def run_recon(left_data, right_data, left_labels, right_labels,
              left_key: str, right_key: str, comparisons,
              left_name: str = "左侧文件", right_name: str = "右侧文件") -> list:
    """执行对账。left_key / right_key / comparisons 中的列用 Excel 字母。"""
    lk = col_index(left_key)
    rk = col_index(right_key)
    if lk is None:
        raise ValueError(f"{left_name}主键列写法不对:「{left_key}」,应类似 A / B / C")
    if rk is None:
        raise ValueError(f"{right_name}主键列写法不对:「{right_key}」,应类似 A / B / C")
    width_l = len(left_data[0]) if left_data else 0
    width_r = len(right_data[0]) if right_data else 0
    if lk >= width_l:
        raise ValueError(f"{left_name}没有第 {left_key} 列(该文件共 {width_l} 列)")
    if rk >= width_r:
        raise ValueError(f"{right_name}没有第 {right_key} 列(该文件共 {width_r} 列)")

    pairs = []
    for c in comparisons:
        lp, rp = col_index(c.get("left")), col_index(c.get("right"))
        if lp is None or rp is None:
            raise ValueError(f"对比列写法不对:「{c.get('left')} / {c.get('right')}」,应类似 D / E")
        if lp >= width_l:
            raise ValueError(f"{left_name}没有第 {c.get('left')} 列(该文件共 {width_l} 列)")
        if rp >= width_r:
            raise ValueError(f"{right_name}没有第 {c.get('right')} 列(该文件共 {width_r} 列)")
        pairs.append({"left": lp, "right": rp, "tolerance": c.get("tolerance"),
                      "left_label": left_labels[lp], "right_label": right_labels[rp]})

    left_index: dict = {}
    for r in left_data:
        left_index.setdefault(norm_key(_cell(r, lk)), []).append(r)
    used = set()

    items = []
    for r in right_data:
        key = norm_key(_cell(r, rk))
        cands = [c for c in left_index.get(key, []) if id(c) not in used]
        if not cands:
            cols = [{"left": p["left_label"], "right": p["right_label"],
                     "left_val": "", "right_val": _cell(r, p["right"]), "equal": False}
                    for p in pairs]
            items.append(ReconItem(kind="table_only", key=str(_cell(r, rk)), cols=cols))
            continue
        l = cands[0]
        used.add(id(l))
        cols = []
        has_diff = False
        for p in pairs:
            lv, rv = _cell(l, p["left"]), _cell(r, p["right"])
            eq = values_equal(lv, rv, p["tolerance"])
            if not eq:
                has_diff = True
            cols.append({"left": p["left_label"], "right": p["right_label"],
                         "left_val": lv, "right_val": rv, "equal": eq})
        items.append(ReconItem(kind="diff" if has_diff else "matched",
                               key=str(_cell(r, rk)), cols=cols))

    for l in left_data:
        if id(l) not in used:
            cols = [{"left": p["left_label"], "right": p["right_label"],
                     "left_val": _cell(l, p["left"]), "right_val": "", "equal": False}
                    for p in pairs]
            items.append(ReconItem(kind="master_only", key=str(_cell(l, lk)), cols=cols))
    return items


def run_recon_multi(master_data, master_labels, master_key, satellites) -> list:
    """多表对比:表一(主表)分别与每张对比表(表二/表三/...)对账。

    satellites: [{name, data, labels, key, comparisons}]
    返回 ReconItem 列表,每条带 table 标识(所属表名)。
    """
    items = []
    for sat in satellites:
        try:
            sub = run_recon(master_data, sat["data"], master_labels, sat["labels"],
                            master_key, sat["key"], sat["comparisons"],
                            left_name="表一", right_name=f"表「{sat['name']}」")
        except ValueError as e:
            raise ValueError(f"[{sat['name']}] {e}")
        for it in sub:
            it.table = sat["name"]
        items.extend(sub)
    return items


def stats(items) -> dict:
    s = {"matched": 0, "diff": 0, "master_only": 0, "table_only": 0, "diff_amount": 0.0}
    for it in items:
        s[it.kind] += 1
        if it.kind == "diff":
            for c in it.cols:
                if c.get("equal"):
                    continue
                l, r = _to_number(c.get("left_val")), _to_number(c.get("right_val"))
                if l is not None and r is not None:
                    s["diff_amount"] = round(s["diff_amount"] + abs(l - r), 2)
    return s


def column_stats(items) -> list:
    """按对比列统计差异:每个 (对比表, 表一列, 对比表列) 的差异条数与数值合计。

    返回: [{table, left, right, count, amount}]
    """
    m: dict = {}
    for it in items:
        if it.kind != "diff":
            continue
        for c in it.cols:
            if c.get("equal"):
                continue
            key = (it.table, c["left"], c["right"])
            s = m.setdefault(key, {"table": it.table, "left": c["left"],
                                   "right": c["right"], "count": 0, "amount": 0.0})
            s["count"] += 1
            l, r = _to_number(c.get("left_val")), _to_number(c.get("right_val"))
            if l is not None and r is not None:
                s["amount"] = round(s["amount"] + abs(l - r), 2)
    return [m[k] for k in m]
