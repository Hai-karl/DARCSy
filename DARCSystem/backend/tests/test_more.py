import os

import pytest

from backend.app import create_app
from backend.seed import seed
from backend.tests.test_api import login
from defect_analysis.sus import sus_score


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    d = tmp_path_factory.mktemp("db3")
    app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("TEST_DATABASE_URL") or f"sqlite:///{d}/t.db",
                      "MODEL_PATH": str(d / "m.joblib"), "TESTING": True})
    seed(app)
    return app.test_client()


def test_sus_scoring():
    assert sus_score([5, 1] * 5) == 100 and sus_score([1, 5] * 5) == 0 and sus_score([3] * 10) == 50
    for bad in ([3] * 9, [0] * 10, [6] * 10, "x"):
        with pytest.raises(ValueError):
            sus_score(bad)


def test_sus_endpoints(client):
    eng, mgr = login(client, "qc.engineer"), login(client, "manager")
    r = client.post("/api/sus", headers=eng, json={"answers": [4, 2, 4, 2, 4, 2, 4, 2, 4, 2]})
    assert r.status_code == 201 and r.json["score"] == 75
    assert client.post("/api/sus", headers=eng, json={"answers": [1, 2]}).status_code == 422
    assert client.get("/api/sus/summary", headers=eng).status_code == 403
    s = client.get("/api/sus/summary", headers=mgr).json
    assert s["n"] == 1 and s["mean"] == 75 and s["by_role"] == {"QC Engineer": 75}


def test_granularity_and_pareto_order(client):
    mgr = login(client, "manager")
    b = client.get("/api/dashboard/bundle", headers=mgr).json
    assert len(b["trend"]["D"]["All"]) > len(b["trend"]["W"]["All"]) > len(b["trend"]["M"]["All"]) >= 6
    for key in ("pareto", "machine", "severity"):
        v = list(b[key]["All"].values())
        assert v == sorted(v, reverse=True)           # ranked order survives JSON


def test_pareto_filters(client):
    mgr = login(client, "manager")
    full = client.get("/api/dashboard/pareto?by=defect_type", headers=mgr).json
    night = client.get("/api/dashboard/pareto?by=defect_type&shift=Night", headers=mgr).json
    early = client.get("/api/dashboard/pareto?by=machine_id&start=2026-01-01&end=2026-02-28", headers=mgr).json
    assert 0 < sum(night.values()) < sum(full.values()) and early
    assert client.get("/api/dashboard/pareto?by=x", headers=mgr).status_code == 422
    assert client.get("/api/dashboard/pareto?by=defect_type&start=2030-01-01", headers=mgr).json == {}


def test_line_scoped_dashboard(client):
    sup, adm = login(client, "supervisor"), login(client, "admin")
    assert client.get("/api/dashboard/bundle", headers=sup).json["lines"] == ["Line A"]
    assert client.get("/api/dashboard/pareto?by=defect_type&line=Line B", headers=sup).json == {}
    r = client.post("/api/users", headers=adm, json={"username": "sup_b", "password": "Password123!",
                                                      "role": "Line Supervisor", "assigned_line": "Line B"})
    assert r.status_code == 201 and r.json["assigned_line"] == "Line B"
