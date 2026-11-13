import os

import pytest

from backend.app import create_app
from backend.seed import seed
from backend.tests.test_api import login

BODY = {"product_id": 15, "defect_type": "Structural", "defect_date": "6/6/2024",
        "defect_location": "Component", "inspection_method": "Visual Inspection"}


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("ml")
    app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{d}/t.db",
                      "MODEL_PATH": str(d / "m.joblib"), "ML_MODEL_DIR": str(d / "models"),
                      "ML_TREES": 15, "TESTING": True})
    seed(app, with_data=False)
    return app.test_client()


def test_schema_before_training_and_predict_conflict(client):
    eng = login(client, "qc.engineer")
    s = client.get("/api/ml/schema", headers=eng).json
    assert [t["trained"] for t in s["targets"]] == [False] * 3 and s["schema"]["product_id"]["max"] == 100
    r = client.post("/api/ml/predict", headers=eng, json={"target": "severity", "inputs": {**BODY, "severity": "x"}})
    assert r.status_code == 409


def test_training_permissions_and_results(client):
    eng, mgr = login(client, "qc.engineer"), login(client, "manager")
    assert client.post("/api/ml/train", headers=eng).status_code == 403
    t = client.post("/api/ml/train", headers=mgr)
    assert t.status_code == 200 and len(t.json) == 3 and all("summary" in x for x in t.json)
    s = client.get("/api/ml/schema", headers=eng).json
    assert all(x["trained"] and x["quality"]["summary"] for x in s["targets"])
    assert len(client.get("/api/ml/metrics", headers=eng).json) == 3


def test_prediction_endpoint(client):
    sup = login(client, "supervisor")
    r = client.post("/api/ml/predict", headers=sup, json={"target": "severity", "inputs": {**BODY}})
    assert r.status_code == 200 and abs(sum(r.json["probabilities"].values()) - 1) < 1e-6
    r = client.post("/api/ml/predict", headers=sup, json={"target": "repair_cost", "inputs": {**BODY, "severity": "Critical"}})
    assert r.status_code == 200 and 10 <= r.json["prediction"] <= 1000 and "warning" in r.json["quality"]
    assert client.post("/api/ml/predict", headers=sup, json={"target": "nope", "inputs": BODY}).status_code == 422


def test_prediction_validation_and_access(client):
    eng, adm = login(client, "qc.engineer"), login(client, "admin")
    r = client.post("/api/ml/predict", headers=eng, json={"target": "defect_type", "inputs": {
        "product_id": 500, "defect_date": "2023-01-01", "defect_location": "Roof", "severity": "Minor",
        "inspection_method": "Visual Inspection", "repair_cost": 5}})
    assert r.status_code == 422 and len(r.json["problems"]) == 4
    assert client.post("/api/ml/predict", headers=adm, json={"target": "severity", "inputs": BODY}).status_code == 403
    assert client.get("/api/ml/schema").status_code == 401
