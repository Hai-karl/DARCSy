import pytest

from backend.app import create_app
from backend.seed import seed

PW = "Str0ngPassw0rd"


def make(tmp, **cfg):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp}/t.db", "MODEL_PATH": str(tmp / "m.joblib"),
                      "ML_MODEL_DIR": str(tmp / "ml"), "TESTING": True, **cfg})
    seed(app, with_data=False)
    return app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    return make(tmp_path_factory.mktemp("auth")).test_client()


def login(c, user, pw="Password123!"):
    return c.post("/api/auth/login", json={"username": user, "password": pw})


def bearer(c, user, pw="Password123!"):
    return {"Authorization": "Bearer " + login(c, user, pw).json["token"]}


REG = {"username": "new.user", "full_name": "New User", "email": "new.user@example.com", "role": "QC Engineer", "password": PW}


def test_registration_validation(client):
    bad = client.post("/api/auth/register", json={"username": "a", "full_name": "", "email": "nope", "role": "IT Administrator", "password": "short"})
    assert bad.status_code == 422 and len(bad.json["problems"]) >= 5
    assert any("IT Administrator" not in p and "Role" in p for p in bad.json["problems"])
    weak = client.post("/api/auth/register", json={**REG, "password": "NEW.user12345"})
    assert weak.status_code == 422 and any("username" in p for p in weak.json["problems"])


def test_register_then_approval_flow(client):
    assert client.post("/api/auth/register", json=REG).status_code == 201
    assert client.post("/api/auth/register", json=REG).status_code == 409                     # same username
    assert client.post("/api/auth/register", json={**REG, "username": "other.name"}).status_code == 409   # same email
    r = login(client, "new.user", PW)
    assert r.status_code == 403 and "waiting for approval" in r.json["error"]
    adm = bearer(client, "admin")
    pending = [u for u in client.get("/api/users", headers=adm).json if u["status"] == "pending"]
    assert pending and pending[0]["username"] == "new.user"
    uid = pending[0]["id"]
    ok = client.patch(f"/api/users/{uid}", headers=adm, json={"status": "active", "role": "Line Supervisor"})
    assert ok.status_code == 200 and ok.json["role"] == "Line Supervisor"
    r = login(client, "new.user", PW)
    assert r.status_code == 200 and "dashboard:view" in r.json["user"]["permissions"]


def test_rejected_and_disabled_cannot_sign_in(client):
    adm = bearer(client, "admin")
    client.post("/api/auth/register", json={**REG, "username": "rej.user", "email": "rej@example.com"})
    uid = [u for u in client.get("/api/users", headers=adm).json if u["username"] == "rej.user"][0]["id"]
    client.patch(f"/api/users/{uid}", headers=adm, json={"status": "rejected"})
    assert login(client, "rej.user", PW).status_code == 403
    assert client.patch(f"/api/users/{uid}", headers=adm, json={"status": "pending"}).status_code == 422


def test_lockout_after_failed_attempts(client):
    for _ in range(5):
        assert login(client, "supervisor", "wrong-password1").status_code == 401
    r = login(client, "supervisor")                                   # right password, but locked
    assert r.status_code == 429 and "locked" in r.json["error"]
    assert login(client, "ghost", "whatever12345").json["error"] == "Wrong username or password."


def test_password_change_revokes_old_tokens(client):
    old = bearer(client, "qc.engineer")
    assert client.post("/api/auth/change-password", headers=old, json={"current_password": "nope", "new_password": PW}).status_code == 403
    assert client.post("/api/auth/change-password", headers=old, json={"current_password": "Password123!", "new_password": "short"}).status_code == 422
    r = client.post("/api/auth/change-password", headers=old, json={"current_password": "Password123!", "new_password": PW})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401                       # old session ended
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer " + r.json["token"]}).status_code == 200
    assert login(client, "qc.engineer", PW).status_code == 200


def test_user_admin_safeguards(client):
    adm = bearer(client, "admin")
    me = client.get("/api/auth/me", headers=adm).json["id"]
    assert client.patch(f"/api/users/{me}", headers=adm, json={"is_active": False}).status_code == 422     # last admin / self
    assert client.patch(f"/api/users/{me}", headers=adm, json={"role": "Quality Manager"}).status_code == 422
    uid = [u for u in client.get("/api/users", headers=adm).json if u["username"] == "manager"][0]["id"]
    tok = bearer(client, "manager")
    client.patch(f"/api/users/{uid}", headers=adm, json={"is_active": False})
    assert client.get("/api/auth/me", headers=tok).status_code == 401                         # disabled: session ends
    assert client.post(f"/api/users/{uid}/reset-password", headers=adm, json={"new_password": "weak"}).status_code == 422
    assert client.post(f"/api/users/{uid}/reset-password", headers=adm, json={"new_password": "Temp0rary-Pass1"}).status_code == 200
    client.patch(f"/api/users/{uid}", headers=adm, json={"is_active": True})
    assert login(client, "manager", "Temp0rary-Pass1").status_code == 200
    assert client.post("/api/auth/logout-all", headers=adm).status_code == 204
    assert client.get("/api/auth/me", headers=adm).status_code == 401


def test_health_and_headers(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json == {"status": "ok"}
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"


def test_rate_limit_and_cors(tmp_path):
    app = make(tmp_path, RATE_LIMIT_FORCE=True, RATE_LOGIN_PER_MIN=3, CORS_ORIGINS="https://app.example.com")
    c = app.test_client()
    codes = [login(c, "ghost", "x" * 12).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    ok = c.get("/api/health", headers={"Origin": "https://app.example.com"})
    bad = c.get("/api/health", headers={"Origin": "https://evil.example.net"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "https://app.example.com"
    assert "Access-Control-Allow-Origin" not in bad.headers


def test_production_refuses_unsafe_settings(tmp_path):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        make(tmp_path, APP_ENV="production", CORS_ORIGINS="https://a.example.com")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        make(tmp_path, APP_ENV="production", SECRET_KEY="x" * 40)
    make(tmp_path, APP_ENV="production", SECRET_KEY="x" * 40, CORS_ORIGINS="https://a.example.com")


def test_bootstrap_admin(tmp_path):
    from backend.models import User
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/b.db", "MODEL_PATH": str(tmp_path / "m.joblib"),
                      "TESTING": True, "BOOTSTRAP_ADMIN_USERNAME": "root.admin", "BOOTSTRAP_ADMIN_PASSWORD": "Boot-Strap-Pass9"})
    with app.app_context():
        assert User.query.filter_by(role="IT Administrator").count() == 1
    assert login(app.test_client(), "root.admin", "Boot-Strap-Pass9").status_code == 200
