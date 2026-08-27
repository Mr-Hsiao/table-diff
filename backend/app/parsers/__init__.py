"""解析器注册表。

- channel: 通用渠道账单解析器(映射驱动,UI 唯一使用的渠道侧解析器)
- pms:     PMS 导出解析器
- ctrip / meituan: 保留用于旧测试的自动识别兼容,UI 不再使用
"""
from .base import BaseParser, parse_amount, parse_date, parse_nights
from .channel import ChannelParser
from .ctrip import CtripParser
from .meituan import MeituanParser
from .pms import PmsParser

PARSERS = {
    "channel": ChannelParser,
    "ctrip": CtripParser,
    "meituan": MeituanParser,
    "pms": PmsParser,
}


def get_parser(channel: str) -> BaseParser:
    if channel not in PARSERS:
        raise ValueError(f"不支持的解析器: {channel},可选: {list(PARSERS)}")
    return PARSERS[channel]()
