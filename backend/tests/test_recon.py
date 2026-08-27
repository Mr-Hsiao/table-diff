"""通用对账引擎单元测试(多表 + Excel 列位置 + 全量对比值)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engine import (col_index, col_letter, column_stats, format_value,
                        norm_key, run_recon, run_recon_multi, stats,
                        values_equal)


def test_col_position():
    assert col_letter(0) == "A" and col_letter(25) == "Z" and col_letter(26) == "AA"
    assert col_index("A") == 0 and col_index("c") == 2 and col_index("AA") == 26
    assert col_index("订单号") is None
    print("col position OK")


def test_key_normalization():
    assert norm_key("1001") == norm_key(1001) == norm_key("1001.0") == "1001"
    assert norm_key("2025/6/1") == "2025-06-01"
    assert norm_key("  ABC  ") == norm_key("abc")
    print("key normalization OK")


def test_values_equal():
    assert values_equal("385.2", "385.20", 0.01)
    assert not values_equal("385.2", "380.2", 0.01)
    assert values_equal("¥349.20", 349.2, 0.01)
    assert values_equal("张三", "张三", None)
    assert not values_equal("张三", "李四", None)
    print("values equal OK")


def test_run_recon_by_position():
    # 表一: A=单号, B=结算金额, C=佣金
    left = [["1001", "349.20", "38.8"],
            ["1002", "698.4", "77.6"],
            ["1003", "529.2", "58.8"],
            ["1004", "412.2", "45.8"]]           # 表一独有
    right = [["1001", "349.2", "38.8"],
             ["1002", "698.4", "77.6"],
             ["1003", "500.0", "58.8"],          # B 列差异
             ["1005", "300", "0"]]               # 表二独有
    items = run_recon(left, right,
                      ["单号", "结算金额", "佣金"], ["单号", "实收", "佣金"],
                      "A", "A",
                      [{"left": "B", "right": "B", "tolerance": 0.01},
                       {"left": "C", "right": "C"}])
    s = stats(items)
    assert s == {"matched": 2, "diff": 1, "master_only": 1, "table_only": 1,
                 "diff_amount": 29.2}, s
    d = next(it for it in items if it.kind == "diff")
    assert d.key == "1003"
    assert len(d.cols) == 2
    assert d.cols[0]["left"] == "结算金额" and d.cols[0]["right"] == "实收"
    assert d.cols[0]["left_val"] == "529.2" and d.cols[0]["right_val"] == "500.0"
    assert d.cols[0]["equal"] is False
    assert d.cols[1]["equal"] is True            # 佣金一致,但仍返回具体值
    # 单边单也带数据:表一独有 -> 左值有,右值空
    mo = next(it for it in items if it.kind == "master_only")
    assert mo.key == "1004" and mo.cols[0]["left_val"] == "412.2" and mo.cols[0]["right_val"] == ""
    to = next(it for it in items if it.kind == "table_only")
    assert to.key == "1005" and to.cols[0]["left_val"] == "" and to.cols[0]["right_val"] == "300"
    print("run_recon by position OK, stats:", s)


def test_run_recon_multi():
    master = [["1001", "349.2"], ["1002", "698.4"], ["1003", "529.2"], ["1006", "900"]]
    master_labels = ["单号", "金额"]
    t2 = [["1001", "349.2"], ["1002", "700.0"], ["1004", "300"]]
    t3 = [["1001", "349.2"], ["1003", "529.2"]]
    satellites = [
        {"name": "表二(PMS)", "data": t2,
         "labels": ["单号", "实收"], "key": "A",
         "comparisons": [{"left": "B", "right": "B", "tolerance": 0.01}]},
        {"name": "表三(美团)", "data": t3,
         "labels": ["单号", "实收"], "key": "A",
         "comparisons": [{"left": "B", "right": "B", "tolerance": 0.01}]},
    ]
    items = run_recon_multi(master, master_labels, "A", satellites)
    s = stats(items)
    # 表二: matched 1001 / diff 1002(差1.6) / master_only 1003,1006 / table_only 1004
    # 表三: matched 1001,1003 / master_only 1002,1006
    assert s == {"matched": 3, "diff": 1, "master_only": 4, "table_only": 1,
                 "diff_amount": 1.6}, s
    d2 = next(it for it in items if it.kind == "diff")
    assert d2.table == "表二(PMS)" and d2.key == "1002"
    mo = next(it for it in items if it.kind == "master_only" and it.key == "1003")
    assert mo.table == "表二(PMS)"               # 1003 在表三存在
    to = next(it for it in items if it.kind == "table_only")
    assert to.key == "1004" and to.table == "表二(PMS)"
    print("run_recon_multi OK, stats:", s)


def test_column_stats():
    left = [["1001", "349.20", "38.8"], ["1002", "698.4", "77.6"]]
    right = [["1001", "340.2", "38.8"], ["1002", "700.4", "70.0"]]
    items = run_recon(left, right,
                      ["单号", "结算金额", "佣金"], ["单号", "实收", "佣金"],
                      "A", "A",
                      [{"left": "B", "right": "B", "tolerance": 0.01},
                       {"left": "C", "right": "C", "tolerance": 0.01}])
    cs = column_stats(items)
    # 结算金额: 1001 差 9.0 + 1002 差 2.0 = 11.0,2 条;佣金: 1002 差 7.6,1 条
    by_left = {c["left"]: c for c in cs}
    assert by_left["结算金额"]["count"] == 2
    assert abs(by_left["结算金额"]["amount"] - 11.0) < 0.01
    assert by_left["佣金"]["count"] == 1
    assert abs(by_left["佣金"]["amount"] - 7.6) < 0.01
    # 汇总金额 = 各列之和
    assert abs(sum(c["amount"] for c in cs) - stats(items)["diff_amount"]) < 0.01
    print("column stats OK:", cs)


def test_format_value():
    assert format_value("385.20") == "385.2"
    assert format_value(38.8) == "38.8"
    assert format_value("未入住") == "未入住"
    print("format value OK")


if __name__ == "__main__":
    test_col_position()
    test_key_normalization()
    test_values_equal()
    test_run_recon_by_position()
    test_run_recon_multi()
    test_column_stats()
    test_format_value()
    print("\n通用引擎测试全部通过 - PASS")
