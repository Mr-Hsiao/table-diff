"""通用渠道账单解析器(映射驱动)。

渠道类型(携程/美团等)不再需要区分 —— 字段映射决定如何解析。
合并了两类渠道账单的通用能力:
- 佣金比例 -> 推导佣金金额(渠道账单常只给比例,如 15%)
- 退款金额 -> 追加备注并归类为已取消
"""
from __future__ import annotations

from .base import BaseParser, parse_amount


class ChannelParser(BaseParser):
    channel = "channel"

    COLUMN_ALIASES = {
        "order_no": ["订单号", "订单编号", "携程订单号", "美团订单号", "渠道订单号",
                     "ota订单号", "外部订单号", "订单id", "order_no"],
        "guest_name": ["入住人", "客人姓名", "客人", "姓名", "入住客人"],
        "room_type": ["房型", "房型名称", "房型/套餐", "商品名称", "套餐名称"],
        "nights": ["间夜", "间夜数", "间夜数量"],
        "check_in": ["入住日期", "到店日期", "ci"],
        "check_out": ["离店日期", "退房日期", "co"],
        "order_amount": ["订单金额", "订单总额", "房费", "房价", "销售金额", "美团价", "应付金额"],
        "commission_amount": ["佣金", "佣金金额", "代理费", "服务费", "佣金(元)"],
        "commission_rate": ["佣金比例", "佣金率", "佣金%"],
        "settle_amount": ["结算金额", "应结算金额", "结算价", "预计结算金额", "实际结算金额"],
        "status": ["订单状态", "状态"],
        "book_time": ["下单时间", "预订时间", "下单日期"],
        "refund_amount": ["退款金额", "已退款金额"],
    }

    def row_to_order(self, row, mapping):
        order = super().row_to_order(row, mapping)
        # 佣金比例推导:有订单金额、缺佣金、但给了比例(如 15% / 0.15)
        if order.order_amount and not order.commission_amount:
            rate = parse_amount(self._cell(row, mapping, "commission_rate"))
            if rate:
                if rate > 1:
                    rate = rate / 100
                order.commission_amount = round(order.order_amount * rate, 2)
                order.settle_amount = round(order.order_amount - order.commission_amount, 2)
        # 退款金额 -> 备注 + 状态归类
        refund = parse_amount(self._cell(row, mapping, "refund_amount"))
        if refund and refund > 0:
            order.remark = (order.remark + " " if order.remark else "") + f"退款{refund:.2f}"
            if order.status == "unknown":
                order.status = "cancelled"
        return order
