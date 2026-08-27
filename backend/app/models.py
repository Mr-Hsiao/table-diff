"""标准化数据模型:所有渠道账单 / PMS 导出统一转成 ParsedOrder,后续逻辑只认这一套口径。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ParsedOrder:
    """一条标准化订单。

    关键口径:
    - order_amount:      订单总额(客人支付价 / 渠道卖价)
    - commission_amount: 佣金(渠道扣的佣金;PMS 侧为已记佣金)
    - settle_amount:     结算金额(渠道: order - commission;PMS: 实收金额)
    - status:            confirmed / cancelled / no_show / unknown
    """

    order_no: str = ""                 # 渠道订单号(用于和 PMS 匹配)
    channel: str = "unknown"           # ctrip / meituan / pms ...
    guest_name: str = ""
    room_type: str = ""
    nights: int = 0
    check_in: str = ""                 # YYYY-MM-DD
    check_out: str = ""
    order_amount: float = 0.0
    commission_amount: float = 0.0
    settle_amount: float = 0.0
    status: str = "unknown"
    book_time: str = ""
    remark: str = ""
    id: Optional[int] = None           # SQLite 主键(保存后赋值)
    raw: dict = field(default_factory=dict)  # 原始行(调试/审计用,默认不导出)

    def to_dict(self, with_raw: bool = False) -> dict:
        d = asdict(self)
        if not with_raw:
            d.pop("raw", None)
        return d


@dataclass
class MatchItem:
    """一条对账结果。kind: matched / diff / channel_only / pms_only"""

    kind: str
    channel_order: Optional[dict] = None
    pms_order: Optional[dict] = None
    diff_amount: float = 0.0
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "channel_order": self.channel_order,
            "pms_order": self.pms_order,
            "diff_amount": self.diff_amount,
            "notes": self.notes,
        }


@dataclass
class MatchResult:
    items: list

    def stats(self) -> dict:
        s = {
            "matched": 0, "diff": 0, "channel_only": 0, "pms_only": 0,
            "diff_amount": 0.0, "channel_settle_total": 0.0,
        }
        for it in self.items:
            s[it.kind] += 1
            s["diff_amount"] = round(s["diff_amount"] + it.diff_amount, 2)
            if it.kind in ("matched", "diff") and it.channel_order:
                s["channel_settle_total"] = round(
                    s["channel_settle_total"] + it.channel_order.get("settle_amount", 0), 2)
        return s
