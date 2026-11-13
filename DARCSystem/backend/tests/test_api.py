import os

import pytest

from backend.app import create_app
from backend.seed import seed


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("db")
    app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{d}/t.db",
                      "MODEL_PATH": str(d / "m.joblib"), "TESTING": True})
    seed(app)
    return app.test_client()


def login(c, user):
    r = c.post("/api/auth/login", json={"username": user, "password": "Password123!"})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json["token"]}


GOOD = dict(inspection_date="2026-08-03", production_line="Line A", product_type="Housing",
            shift="Morning", machine_id="M-01", defect_type="Scratch",
            batch_number="B260803-AM", severity="Minor", units_inspected=200, defect_count=4, temperature=27.5, humidity=61)


def test_login_and_bad_login(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    assert client.get("/api/records").status_code == 401


def test_record_validation_and_create(client):
    h = login(client, "qc.engineer")
    bad = client.post("/api/records", json={**GOOD, "defect_count": 999}, headers=h)
    assert bad.status_code == 422 and "exceed" in bad.json["problems"][0]
    ok = client.post("/api/records", json=GOOD, headers=h)
    assert ok.status_code == 201 and ok.json["created"] == 1


def test_rbac_enforced(client):
    sup = login(client, "supervisor")
    assert client.post("/api/records", json=GOOD, headers=sup).status_code == 403
    assert client.get("/api/dashboard/bundle", headers=sup).status_code == 200
    adm = login(client, "admin")
    assert client.get("/api/dashboard/bundle", headers=adm).status_code == 403
    assert client.get("/api/users", headers=adm).status_code == 200
    assert client.get("/api/users", headers=sup).status_code == 403


def test_model_train_predict_and_bundle(client):
    mgr, eng = login(client, "manager"), login(client, "qc.engineer")
    assert client.post("/api/rootcause/predict", json=GOOD, headers=eng).status_code == 409
    assert client.post("/api/model/train", headers=eng).status_code == 403
    t = client.post("/api/model/train", headers=mgr)
    assert t.status_code == 200 and t.json["accuracy"] > 0.5
    p = client.post("/api/rootcause/predict", json=GOOD, headers=eng)
    assert p.status_code == 200 and "suggestion_1" in p.json["suggestions"][0]
    b = client.get("/api/dashboard/bundle", headers=mgr).json
    assert set(b["weekly"]) >= {"All", "Line A"} and b["pred"] and b["acc"]


def test_summary_and_user_admin(client):
    mgr, adm = login(client, "manager"), login(client, "admin")
    s = client.get("/api/dashboard/summary?line=Line B&freq=MS", headers=mgr)
    assert s.status_code == 200 and "control_chart" in s.json
    r = client.post("/api/users", headers=adm, json={"username": "new1", "password": "Password123!", "role": "QC Engineer"})
    assert r.status_code == 201
    assert client.post("/api/users", headers=adm, json={"username": "x", "password": "short", "role": "QC Engineer"}).status_code == 422
