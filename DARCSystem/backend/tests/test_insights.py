import os

import pandas as pd
import pytest

from backend.app import create_app
from backend.seed import seed
from backend.tests.test_api import GOOD, login
from defect_analysis import prepare_records
from defect_analysis.analytics import period_bounds, similar_periods, what_changed


def _row(date, machine, units, defects, shift="Morning", dtype=None):
    return dict(inspection_date=date, production_line="Line A", product_type="Housing", shift=shift,
                machine_id=machine, defect_type=dtype or ("Scratch" if defects else "None"), batch_number="B1",
                severity="Minor" if defects else "None", units_inspected=units, defect_count=defects)


def test_what_changed_finds_the_machine_that_jumped():
    rows = []
    for w in range(10):                                   # 10 weeks, two machines
        for d in range(7):
            day = pd.Timestamp("2026-03-02") + pd.Timedelta(days=7 * w + d)
            spike = w == 9
            rows += [_row(day, "M-01", 200, 16 if spike else 2), _row(day, "M-02", 200, 2)]
    df = prepare_records(pd.DataFrame(rows))
    r = what_changed(df, "2026-05-04", "2026-05-10")
    assert r["drivers"][0]["dimension"] == "Machine" and r["drivers"][0]["value"] == "M-01"
    assert r["drivers"][0]["extra_defects"] > 50 and r["period"]["rate"] > r["baseline"]["rate"]
    assert what_changed(df, "2026-03-02", "2026-03-08")["drivers"] == []        # nothing earlier to compare


def test_similar_periods_ranks_matching_mix_first():
    rows = []
    for w in range(6):
        for d in range(7):
            day = pd.Timestamp("2026-03-02") + pd.Timedelta(days=7 * w + d)
            night = w in (1, 4)                           # weeks 1 and 4 look alike: Night shift, M-02
            rows += [_row(day, "M-02" if night else "M-01", 200, 6, "Night" if night else "Morning")]
    df = prepare_records(pd.DataFrame(rows))
    res = similar_periods(df, "2026-03-09", "2026-03-15", "W")          # week 1
    assert res[0]["start"] == "2026-03-30" and res[0]["similarity"] > 0.99      # week 4 (starts 30 Mar)
    assert all(not (r["start"] <= "2026-03-15" and r["end"] >= "2026-03-09") for r in res)
    assert period_bounds("2026-03-15", "W")[0] == pd.Timestamp("2026-03-09")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("db4")
    app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{d}/t.db",
                      "MODEL_PATH": str(d / "m.joblib"), "TESTING": True})
    seed(app)
    return app.test_client()


def test_endpoints_and_events(client):
    mgr, eng, sup, adm = (login(client, u) for u in ("manager", "qc.engineer", "supervisor", "admin"))
    b = client.get("/api/dashboard/bundle", headers=mgr).json
    row = b["trend"]["W"]["All"][-5]
    assert len(row) == 5 and row[3] <= row[4]
    q = f"start={row[3]}&end={row[4]}"
    w = client.get(f"/api/dashboard/what-changed?{q}", headers=mgr).json
    assert w["period"]["rate"] is not None and w["suggested_causes"] == []          # model not trained yet
    assert all(w["drivers"][i]["extra_defects"] >= w["drivers"][i + 1]["extra_defects"] for i in range(len(w["drivers"]) - 1))
    client.post("/api/model/train", headers=mgr)
    assert len(client.get(f"/api/dashboard/what-changed?{q}&line=Line B", headers=mgr).json["suggested_causes"]) == 3
    s = client.get(f"/api/dashboard/similar?{q}&freq=W", headers=mgr).json["results"]
    assert 0 < len(s) <= 5 and all(0 <= r["similarity"] <= 1 for r in s)
    assert client.get("/api/dashboard/what-changed?start=bad", headers=mgr).status_code == 422
    assert client.get(f"/api/dashboard/similar?{q}&freq=X", headers=mgr).status_code == 422
    assert client.get(f"/api/dashboard/what-changed?{q}", headers=adm).status_code == 403
    sl = client.get(f"/api/dashboard/similar?{q}&freq=W", headers=sup).json["results"]
    assert all(r["line"] == "Line A" for r in sl)                                      # supervisor scope
    a = client.post("/api/corrective-actions", headers=eng, json={"production_line": "Line B", "root_cause": "Machine",
                                                                  "description": "Replace guide rails"}).json["id"]
    client.post(f"/api/corrective-actions/{a}/approve", headers=mgr)
    client.post(f"/api/corrective-actions/{a}/implement", headers=eng, json={"date": "2026-04-15"})
    client.post("/api/records", headers=eng, json={**GOOD, "severity": "Safety-Critical", "defect_count": 1})
    ev = client.get("/api/events", headers=mgr).json
    assert {"kind": "action", "date": "2026-04-15", "line": "Line B", "label": "Replace guide rails"} in ev
    assert any(e["kind"] == "alert" for e in ev)
    assert all(e["line"] == "Line A" for e in client.get("/api/events", headers=sup).json)
