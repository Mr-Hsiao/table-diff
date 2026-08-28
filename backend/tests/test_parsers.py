"""解析器单元测试(不依赖 pytest,直接运行也可: python tests/test_parsers.py)。"""
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers import get_parser
from app.parsers.pms import PmsParser

SAMPLES = Path(__file__).parent / "samples"


def test_amount_and_date():
    from app.parsers.base import parse_amount, parse_date
    assert parse_amount("¥1,234.56") == 1234.56
    assert parse_amount("1,234.56元") == 1234.56
    assert parse_amount("—") == 0.0
    assert parse_amount("(100)") == -100.0
    assert parse_amount("15%") == 15.0
    assert parse_amount(None) == 0.0
    assert parse_date("2025/6/1") == "2025-06-01"
    assert parse_date("2025年6月1日") == "2025-06-01"
    assert parse_date("2025-06-01 12:30:00") == "2025-06-01"
    print("amount/date OK")


def test_ctrip_parse():
    # 样例文件可能被外部改动,这里只做结构性断言(数量/首行/状态),数值细节用自建文件测试
    orders = get_parser("ctrip").parse_file(SAMPLES / "ctrip_settlement_sample.csv")
    assert len(orders) == 10
    o = orders[0]
    assert o.order_no == "1001"
    assert next(x for x in orders if x.order_no == "1005").status == "cancelled"
    assert next(x for x in orders if x.order_no == "1006").status == "no_show"
    print("ctrip parse OK(结构性)")


def test_commission_rate_derivation():
    # 佣金比例推导:有金额、无佣金、给比例 -> 自动算佣金与结算(自建文件,不依赖样例)
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    w.writerow(["订单号", "金额", "佣金比例"])
    w.writerow(["9001", 388, "15%"])
    f.close()
    try:
        orders = get_parser("ctrip").parse_file(f.name)
        o = orders[0]
        assert abs(o.commission_amount - 58.2) < 0.01
        assert abs(o.settle_amount - 329.8) < 0.01
        print("commission rate derivation OK")
    finally:
        Path(f.name).unlink(missing_ok=True)


def test_meituan_parse():
    orders = get_parser("meituan").parse_file(SAMPLES / "meituan_bill_sample.csv")
    assert len(orders) == 8
    assert next(x for x in orders if x.order_no == "2001").settle_amount == 322.2
    assert next(x for x in orders if x.order_no == "2004").status == "cancelled"
    print("meituan parse OK")


def test_pms_parse():
    orders = PmsParser().parse_file(SAMPLES / "pms_export_sample.csv")
    assert len(orders) == 17
    direct = [x for x in orders if x.order_no == ""]
    assert len(direct) == 1  # 直客单没有渠道订单号
    print("pms parse OK")


if __name__ == "__main__":
    test_amount_and_date()
    test_ctrip_parse()
    test_commission_rate_derivation()
    test_meituan_parse()
    test_pms_parse()
    print("\n全部解析器测试通过 - PASS")
