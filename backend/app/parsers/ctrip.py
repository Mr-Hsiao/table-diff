"""携程结算单解析器。"""
from __future__ import annotations

from .base import BaseParser, parse_amount


class CtripParser(BaseParser):
    channel = "ctrip"

    COLUMN_ALIASES = {
        "order_no": ["订单号", "订单编号", "携程订单号", "订单id", "order_no"],
        "guest_name": ["入住人", "客人姓名", "客人", "姓名", "入住客人"],
        "room_type": ["房型", "房型名称", "房型/套餐"],
        "nights": ["间夜", "间夜数", "间夜数量"],
        "check_in": ["入住日期", "到店日期", "ci"],
        "check_out": ["离店日期", "退房日期", "co"],
        "order_amount": ["订单金额", "订单总额", "房费", "房价", "销售金额"],
        "commission_amount": ["佣金", "佣金金额", "代理费", "佣金(元)"],
        "commission_rate": ["佣金比例", "佣金率", "佣金%"],
        "settle_amount": ["结算金额", "应结算金额", "结算价"],
        "status": ["订单状态", "状态"],
        "book_time": ["下单时间", "预订时间", "下单日期"],
    }

    def row_to_order(self, row, mapping):
        order = super().row_to_order(row, mapping)
        # 有订单金额但缺佣金时,用佣金比例推导(携程常见只给比例)
        if order.order_amount and not order.commission_amount:
            rate = parse_amount(self._cell(row, mapping, "commission_rate"))
            if rate:
                if rate > 1:  # 15 -> 0.15
                    rate = rate / 100
                order.commission_amount = round(order.order_amount * rate, 2)
                order.settle_amount = round(order.order_amount - order.commission_amount, 2)
        return order
