"""对真实运行中服务(表对比工具)的完整流程验证。"""
import json
import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8765"
SAMPLES = Path(__file__).parent / "samples"


def main():
    with httpx.Client(base_url=BASE, timeout=15) as c:
        # 预览两张样例表
        with open(SAMPLES / "ctrip_settlement_sample.csv", "rb") as f:
            r = c.post("/api/preview", data={"has_header": "1"},
                       files={"file": ("ctrip.csv", f, "text/csv")})
        assert r.status_code == 200, r.text
        pv = r.json()
        print("PREVIEW 表一: key=%s labels=%s" % (pv["suggested_key"], pv["labels"][:3]))

        with open(SAMPLES / "pms_export_sample.csv", "rb") as f:
            r = c.post("/api/preview", data={"has_header": "1"},
                       files={"file": ("pms.csv", f, "text/csv")})
        print("PREVIEW 表二: key=%s" % r.json()["suggested_key"])

        # 建多表映射:表一(携程账单)主键A, 表二(PMS流水)主键B, 对比 J↔J、I↔I
        tables = json.dumps([
            {"name": "携程账单", "key": "A", "has_header": 1, "comparisons": []},
            {"name": "PMS流水", "key": "B", "has_header": 1,
             "comparisons": [
                 {"left": "J", "right": "J", "tolerance": 0.01},
                 {"left": "I", "right": "I", "tolerance": 0.01},
             ]},
        ], ensure_ascii=False)
        r = c.post("/api/plans", data={"name": "携程对PMS(样例)", "tables": tables})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        print("PLAN created:", pid)

        with open(SAMPLES / "ctrip_settlement_sample.csv", "rb") as f1, \
             open(SAMPLES / "pms_export_sample.csv", "rb") as f2:
            r = c.post("/api/recon", data={"plan_id": pid},
                       files=[("files", ("ctrip.csv", f1, "text/csv")),
                              ("files", ("pms.csv", f2, "text/csv"))])
        assert r.status_code == 200, r.text
        res = r.json()
        print("RECON stats:", json.dumps(res["stats"], ensure_ascii=False))
        run_id = res["run_id"]
        diff = [it for it in res["items"] if it["kind"] == "diff"]
        print("DIFF sample:", diff[0]["key"], diff[0]["table"], diff[0]["cols"])
        mo = [it for it in res["items"] if it["kind"] == "master_only"]
        print("MASTER_ONLY:", [(it["key"], it["table"]) for it in mo])

        r = c.get(f"/api/export/{run_id}")
        assert r.status_code == 200
        text = r.content.decode("utf-8-sig")
        assert "1008" in text and "统计" in text
        assert "与【PMS流水】对比" in text
        assert "携程账单·" in text and "PMS流水·" in text          # 表头 = 表名·列名
        assert "「携程账单」有,「PMS流水」无" in text               # 用映射表名措辞
        assert "差异合计" in text
        assert "列差异统计" in text                                 # 按列差异统计
        print("EXPORT OK,", len(r.content), "bytes")

        c.delete(f"/api/plans/{pid}")
        print("cleanup OK - 真实HTTP多表流程验证通过")


if __name__ == "__main__":
    main()
