import os

import pytest

from backend.app import create_app
from backend.seed import seed
from backend.tests.test_api import GOOD, login


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("db2")
    app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{d}/t.db",
                      "MODEL_PATH": str(d / "m.joblib"), "TESTING": True})
    seed(app)
    return app.test_client()


def test_safety_critical_alert_and_ack(client):
    eng, sup = login(client, "qc.engineer"), login(client, "supervisor")
    r = client.post("/api/records", headers=eng, json={**GOOD, "severity": "Safety-Critical", "defect_count": 1})
    assert r.status_code == 201
    al = client.get("/api/alerts?open=1", headers=sup).json
    safety = [a for a in al if a["kind"] == "safety"]
    assert safety and safety[0]["email_status"] == "not_configured"
    assert client.post(f"/api/alerts/{safety[0]['id']}/ack", headers=eng).status_code == 403
    assert client.post(f"/api/alerts/{safety[0]['id']}/ack", headers=sup).status_code == 200
    assert not [a for a in client.get("/api/alerts?open=1", headers=sup).json if a["kind"] == "safety"]


def test_threshold_alert_email_failure_and_retry(client):
    mgr, eng = login(client, "manager"), login(client, "qc.engineer")
    assert client.put("/api/thresholds", headers=eng, json={"production_line": "Line C", "max_defect_rate": .01}).status_code == 403
    assert client.put("/api/thresholds", headers=mgr, json={"production_line": "Line C", "max_defect_rate": 5}).status_code == 422
    assert client.put("/api/thresholds", headers=mgr, json={"production_line": "Line C", "max_defect_rate": .001}).status_code == 200

    def broken(to, subject, body):
        raise ConnectionError("mail server down")
    sent = []
    client.application.mailer = broken
    rec = {**GOOD, "production_line": "Line C", "machine_id": "M-05", "defect_count": 30}
    assert client.post("/api/records", headers=eng, json=rec).status_code == 201
    th = [a for a in client.get("/api/alerts?open=1", headers=mgr).json
          if a["kind"] == "threshold" and a["production_line"] == "Line C"]
    assert len(th) == 1 and th[0]["email_status"] == "failed"       # in-app alert still shown
    client.post("/api/records", headers=eng, json=rec)               # no duplicate while open
    assert len([a for a in client.get("/api/alerts?open=1", headers=mgr).json
                if a["kind"] == "threshold" and a["production_line"] == "Line C"]) == 1
    client.application.mailer = lambda to, s, b: sent.append(to)
    assert client.post("/api/alerts/retry-emails", headers=mgr).json["sent"] >= 1 and sent


def test_corrective_action_lifecycle_and_effectiveness(client):
    eng, mgr, sup = login(client, "qc.engineer"), login(client, "manager"), login(client, "supervisor")
    body = {"production_line": "Line B", "machine_id": "M-03", "defect_type": "Scratch",
            "root_cause": "Machine", "suggested_cause": "Machine", "description": "Replace worn guide rails"}
    assert client.post("/api/corrective-actions", headers=sup, json=body).status_code == 403
    a = client.post("/api/corrective-actions", headers=eng, json=body)
    assert a.status_code == 201
    aid = a.json["id"]
    assert client.post(f"/api/corrective-actions/{aid}/implement", headers=eng, json={}).status_code == 422
    assert client.post(f"/api/corrective-actions/{aid}/approve", headers=eng).status_code == 403
    assert client.post(f"/api/corrective-actions/{aid}/approve", headers=mgr).status_code == 200
    assert client.post(f"/api/corrective-actions/{aid}/implement", headers=eng, json={"date": "2026-04-15"}).status_code == 200
    e = client.get(f"/api/corrective-actions/{aid}/effectiveness", headers=mgr).json
    assert e["status"] in ("improved", "worse", "no clear change") and e["change_pct"] is not None
    assert client.get("/api/model/agreement", headers=mgr).json == {"n": 1, "rate": 1.0}


def test_investigate_metrics_heatmap_reports(client):
    mgr, eng, sup = login(client, "manager"), login(client, "qc.engineer"), login(client, "supervisor")
    assert client.post("/api/rootcause/investigate", headers=eng, json={}).status_code == 409
    m = client.post("/api/model/train", headers=mgr)
    assert m.status_code == 200
    inv = client.post("/api/rootcause/investigate", headers=eng, json={"defect_type": "Scratch"}).json
    assert inv["ranked"][0]["confidence"] >= inv["ranked"][-1]["confidence"] and "rules" in inv
    tiny = client.post("/api/rootcause/investigate", headers=eng, json={"defect_type": "Scratch", "line": "Line A",
                                                                          "machine": "M-01", "shift": "Night"}).json
    assert "message" in tiny
    b = client.get("/api/dashboard/bundle", headers=mgr).json
    assert len(b["heat"]["labels"]) == len(b["heat"]["matrix"]) > 5
    assert {"precision", "recall", "benchmark"} <= set(b["metrics"])
    x = client.get("/api/reports/quality?format=xlsx", headers=eng)
    assert x.status_code == 200 and x.data[:2] == b"PK"
    p = client.get("/api/reports/quality?format=pdf", headers=mgr)
    assert p.status_code == 200 and p.data[:4] == b"%PDF"
    assert client.get("/api/reports/quality", headers=sup).status_code == 403
