"""PMS 营业导出解析器(通用模板)。

PMS 侧匹配的关键是「渠道订单号」列(酒店把 OTA 订单号记进 PMS)。
不同 PMS 列名略有差异,在这里加别名即可;建议导出模板字段:
内部单号, 渠道订单号, 客人, 房型, 入住日期, 离店日期, 间夜, 房费, 佣金, 实收金额, 来源渠道, 状态
"""
from __future__ import annotations

from .base import BaseParser


class PmsParser(BaseParser):
    channel = "pms"
    keep_rows_without_order_no = True  # 直客单保留,用于「PMS有单渠道无单」检查

    COLUMN_ALIASES = {
        "order_no": ["渠道订单号", "ota订单号", "外部订单号", "携程订单号", "美团订单号", "订单号"],
        "guest_name": ["客人", "客人姓名", "宾客", "姓名", "入住人"],
        "room_type": ["房型", "房型名称"],
        "nights": ["间夜", "间夜数"],
        "check_in": ["入住日期", "到店日期"],
        "check_out": ["离店日期", "退房日期"],
        "order_amount": ["房费", "房价", "应收", "订单金额", "销售金额"],
        "commission_amount": ["佣金", "佣金金额", "渠道佣金"],
        "settle_amount": ["实收", "实收金额", "结算金额"],
        "status": ["状态", "订单状态"],
        "book_time": ["下单时间", "预订时间", "创建时间"],
    }

    STATUS_MAP = {
        "confirmed": ["已离店", "已入住", "在住", "完成", "已结算", "正常", "有效", "confirmed", "checked"],
        "cancelled": ["取消", "退订", "cancelled", "canceled", "cancel"],
        "no_show": ["未入住", "noshow", "no-show", "no show", "未到店"],
    }
