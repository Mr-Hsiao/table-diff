"""美团账单解析器。"""
from __future__ import annotations

from .base import BaseParser, parse_amount


class MeituanParser(BaseParser):
    channel = "meituan"

    COLUMN_ALIASES = {
        "order_no": ["订单编号", "订单号", "美团订单号", "订单id"],
        "guest_name": ["客人姓名", "入住人", "姓名"],
        "room_type": ["房型", "商品名称", "房型名称", "套餐名称"],
        "nights": ["间夜", "间夜数"],
        "check_in": ["入住日期", "到店日期"],
        "check_out": ["离店日期", "退房日期"],
        "order_amount": ["订单金额", "订单总额", "美团价", "销售金额", "应付金额"],
        "commission_amount": ["佣金", "佣金金额", "服务费"],
        "settle_amount": ["结算金额", "预计结算金额", "实际结算金额"],
        "status": ["订单状态", "状态"],
        "book_time": ["下单时间", "预订时间"],
        "refund_amount": ["退款金额", "已退款金额"],
    }

    def row_to_order(self, row, mapping):
        order = super().row_to_order(row, mapping)
        refund = parse_amount(self._cell(row, mapping, "refund_amount"))
        if refund and refund > 0:
            order.remark = (order.remark + " " if order.remark else "") + f"退款{refund:.2f}"
            if order.status == "unknown":
                order.status = "cancelled"
        return order
