"""API 端到端测试(表对比工具,表一/表二... + Excel 列位置)。"""
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.main import app


def _write_csv(headers, rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8-sig")
    w = csv.writer(f)
    w.writerow(headers)
    w.writerows(rows)
    f.close()
    return f.name


def _tables(name1, name2, key1, key2, comps, hh1=1, hh2=1):
    return json.dumps([
        {"name": name1, "key": key1, "has_header": hh1, "comparisons": []},
        {"name": name2, "key": key2, "has_header": hh2, "comparisons": comps},
    ], ensure_ascii=False)


def test_static_page():
    with TestClient(app) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert "表对比" in r.text
        for asset in ("/style.css", "/app.js", "/vendor/vue.global.prod.js"):
            ar = client.get(asset)
            assert ar.status_code == 200, f"{asset} -> {ar.status_code}"
    print("static page OK")


def test_preview_plans_recon_export():
    t1_headers = ["订单号", "结算金额", "佣金"]
    t1_rows = [["1001", "349.2", "38.8"], ["1002", "698.4", "77.6"], ["1003", "529.2", "58.8"]]
    t2_headers = ["渠道单号", "实收金额", "佣金"]
    t2_rows = [["1001", "349.2", "38.8"], ["1002", "698.4", "77.6"],
               ["1003", "500.0", "58.8"], ["1005", "300", "0"]]
    t1 = _write_csv(t1_headers, t1_rows)
    t2 = _write_csv(t2_headers, t2_rows)
    try:
        with TestClient(app) as client:
            # 预览:建议主键/对比列(列字母)
            with open(t1, "rb") as f:
                r = client.post("/api/preview", data={"has_header": "1"},
                                files={"file": ("t1.csv", f, "text/csv")})
            assert r.status_code == 200, r.text
            pv = r.json()
            assert pv["suggested_key"] == "A"          # 订单号在 A 列
            assert "B" in pv["suggested_compare"]
            assert pv["labels"][0] == "A(订单号)"
            print("preview OK:", pv["suggested_key"], pv["suggested_compare"])

            # 新建方案(表一 + 表二,列字母)
            tables = _tables("携程账单", "PMS流水", "A", "A",
                             [{"left": "B", "right": "B", "tolerance": 0.01},
                              {"left": "C", "right": "C", "tolerance": 0.01}])
            r = client.post("/api/plans", data={"name": "携程对PMS", "tables": tables})
            assert r.status_code == 200, r.text
            pid = r.json()["id"]

            r = client.get("/api/plans")
            plan = next(p for p in r.json()["plans"] if p["id"] == pid)
            assert plan["tables"][0]["name"] == "携程账单"
            assert plan["tables"][1]["comparisons"][0]["left"] == "B"
            print("plan create/list OK")

            # 执行对账(两个文件)
            with open(t1, "rb") as f1, open(t2, "rb") as f2:
                r = client.post("/api/recon", data={"plan_id": pid},
                                files=[("files", ("t1.csv", f1, "text/csv")),
                                       ("files", ("t2.csv", f2, "text/csv"))])
            assert r.status_code == 200, r.text
            res = r.json()
            assert res["stats"] == {"matched": 2, "diff": 1, "master_only": 0,
                                    "table_only": 1, "diff_amount": 29.2}, res["stats"]
            # 按列差异统计:仅 结算金额↔实收金额 有差异(29.2,1条);佣金一致不计
            cs = {c["left"]: c for c in res["col_stats"]}
            assert cs["结算金额"]["count"] == 1 and abs(cs["结算金额"]["amount"] - 29.2) < 0.01
            assert "佣金" not in cs
            run_id = res["run_id"]
            diff_item = next(it for it in res["items"] if it["kind"] == "diff")
            assert diff_item["key"] == "1003" and diff_item["table"] == "PMS流水"
            assert diff_item["cols"][0]["left"] == "结算金额"
            assert diff_item["cols"][0]["right"] == "实收金额"
            assert diff_item["cols"][0]["equal"] is False
            assert diff_item["cols"][1]["equal"] is True
            print("recon OK:", res["stats"])

            # 导出:按对比表分组,表头带 表名·列名,末尾统计
            r = client.get(f"/api/export/{run_id}")
            assert r.status_code == 200
            text = r.text
            assert "与【PMS流水】对比" in text
            assert "携程账单·结算金额" in text
            assert "PMS流水·实收金额" in text
            assert "1003" in text and "统计" in text
            assert "「携程账单」独有" in text and "「PMS流水」独有" in text
            assert "差异合计 29.20" in text
            assert "列差异统计" in text and "结算金额" in text
            print("export OK")

            # 更新 + 删除
            r = client.put(f"/api/plans/{pid}", data={"name": "改名", "tables": tables})
            assert r.status_code == 200
            r = client.delete(f"/api/plans/{pid}")
            assert r.status_code == 200
            print("plan update/delete OK")
    finally:
        Path(t1).unlink(missing_ok=True)
        Path(t2).unlink(missing_ok=True)


def test_three_tables():
    # 表一 + 表二 + 表三(三表对比)
    t1 = _write_csv(["单号", "金额"], [["1001", "349.2"], ["1002", "698.4"]])
    t2 = _write_csv(["单号", "金额"], [["1001", "349.2"], ["1003", "500"]])
    t3 = _write_csv(["单号", "金额"], [["1001", "349.2"], ["1002", "698.4"]])
    try:
        with TestClient(app) as client:
            tables = json.dumps([
                {"name": "总账", "key": "A", "has_header": 1, "comparisons": []},
                {"name": "流水A", "key": "A", "has_header": 1,
                 "comparisons": [{"left": "B", "right": "B", "tolerance": 0.01}]},
                {"name": "流水B", "key": "A", "has_header": 1,
                 "comparisons": [{"left": "B", "right": "B", "tolerance": 0.01}]},
            ], ensure_ascii=False)
            r = client.post("/api/plans", data={"name": "三表", "tables": tables})
            assert r.status_code == 200, r.text
            pid = r.json()["id"]
            with open(t1, "rb") as f1, open(t2, "rb") as f2, open(t3, "rb") as f3:
                r = client.post("/api/recon", data={"plan_id": pid},
                                files=[("files", ("t1.csv", f1, "text/csv")),
                                       ("files", ("t2.csv", f2, "text/csv")),
                                       ("files", ("t3.csv", f3, "text/csv"))])
            assert r.status_code == 200, r.text
            s = r.json()["stats"]
            # 对流水A: 1001一致/1002表一独有/1003流水A独有;对流水B: 全一致
            assert s == {"matched": 3, "diff": 0, "master_only": 1,
                         "table_only": 1, "diff_amount": 0.0}, s
            # 表名识别: master_only 来自流水A
            mo = next(it for it in r.json()["items"] if it["kind"] == "master_only")
            assert mo["table"] == "流水A" and mo["key"] == "1002"
            print("three-tables OK:", s)
            client.delete(f"/api/plans/{pid}")
    finally:
        Path(t1).unlink(missing_ok=True)
        Path(t2).unlink(missing_ok=True)
        Path(t3).unlink(missing_ok=True)


def test_file_count_mismatch():
    t1 = _write_csv(["单号"], [["1"]])
    t2 = _write_csv(["单号"], [["1"]])
    try:
        with TestClient(app) as client:
            tables = _tables("表一", "表二", "A", "A", [])
            r = client.post("/api/plans", data={"name": "计数", "tables": tables})
            pid = r.json()["id"]
            with open(t1, "rb") as f1:
                r = client.post("/api/recon", data={"plan_id": pid},
                                files=[("files", ("t1.csv", f1, "text/csv"))])
            assert r.status_code == 400
            assert "需要上传 2 个文件" in r.json()["detail"]
            print("file-count error OK")
            client.delete(f"/api/plans/{pid}")
    finally:
        Path(t1).unlink(missing_ok=True)
        Path(t2).unlink(missing_ok=True)


def test_missing_column_error():
    t1 = _write_csv(["A列"], [["x"]])
    t2 = _write_csv(["单号"], [["1"]])
    try:
        with TestClient(app) as client:
            tables = _tables("表一", "表二", "F", "A", [])
            r = client.post("/api/plans", data={"name": "错列", "tables": tables})
            assert r.status_code == 200
            pid = r.json()["id"]
            with open(t1, "rb") as f1, open(t2, "rb") as f2:
                r = client.post("/api/recon", data={"plan_id": pid},
                                files=[("files", ("t1.csv", f1, "text/csv")),
                                       ("files", ("t2.csv", f2, "text/csv"))])
            assert r.status_code == 400
            assert "没有第 F 列" in r.json()["detail"]
            print("missing-column error OK")
            client.delete(f"/api/plans/{pid}")
    finally:
        Path(t1).unlink(missing_ok=True)
        Path(t2).unlink(missing_ok=True)


if __name__ == "__main__":
    test_static_page()
    test_preview_plans_recon_export()
    test_three_tables()
    test_file_count_mismatch()
    test_missing_column_error()
    print("\nAPI 测试全部通过 - PASS")
