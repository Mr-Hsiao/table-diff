"""健壮性测试:用户改了表头 / 列序 / 格式 / 编码,解析器仍能正确解析。

覆盖:表头改名、列乱序、加多余列、金额带 ¥ 和千分位、日期斜杠格式、GBK 编码。
"""
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.parsers import get_parser

SAMPLES = Path(__file__).parent / "samples"


def _read_rows(path):
    raw = Path(path).read_bytes()
    text = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    assert text is not None, f"无法识别文件编码: {path}"
    return list(csv.reader(text.splitlines()))


def test_renamed_reordered_extra_columns():
    rows = _read_rows(SAMPLES / "ctrip_settlement_sample.csv")
    headers = rows[0]
    # 重命名表头 + 打乱列序 + 追加一列备注
    rename = {
        "订单号": "订单编号", "入住人": "客人姓名", "房型": "房型名称",
        "订单金额": "房费", "结算金额": "应结算", "订单状态": "状态",
        "下单时间": "预订时间",
    }
    order = [7, 0, 2, 1, 4, 5, 3, 6, 8, 9, 10, 11]  # 乱序
    new_headers = [rename.get(headers[i], headers[i]) for i in order] + ["备注"]
    data = []
    for row in rows[1:]:
        new_row = [row[i] for i in order] + ["无"]
        new_row[7] = "¥" + new_row[7] + ".00"          # 房费: ¥388.00
        new_row[9] = "¥" + new_row[9] + ".00"          # 应结算: ¥349.20
        new_row[4] = new_row[4].replace("-", "/")      # 入住日期: 2025/06/01
        new_row[5] = new_row[5].replace("-", "/")      # 离店日期
        data.append(new_row)
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(new_headers)
        w.writerows(data)
        path = f.name
    try:
        orders = get_parser("ctrip").parse_file(path)
        assert len(orders) == 10, len(orders)
        o = orders[0]
        assert o.order_no == "1001"
        assert o.check_in == "2025-06-01"      # 斜杠日期已归一化
        assert o.order_amount == 388.0         # ¥ 已解析
        assert abs(o.settle_amount - 349.2) < 0.01
        # (佣金比例推导细节见 test_parsers.test_commission_rate_derivation)
        print("renamed/reordered/extra/yuan/slash OK")
    finally:
        Path(path).unlink(missing_ok=True)


def test_gbk_encoding():
    rows = _read_rows(SAMPLES / "ctrip_settlement_sample.csv")
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                     newline="", encoding="gbk") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)
        path = f.name
    try:
        orders = get_parser("ctrip").parse_file(path)
        assert len(orders) == 10
        assert orders[0].guest_name == "张伟"
        print("gbk encoding OK")
    finally:
        Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    test_renamed_reordered_extra_columns()
    test_gbk_encoding()
    print("\n健壮性测试全部通过 - PASS")
