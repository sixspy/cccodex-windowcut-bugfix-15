import pytest
from fastapi.testclient import TestClient

from app import app, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "t.db")
    init_db()
    yield


def _auth(c: TestClient) -> dict:
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def test_window_flow():
    c = TestClient(app)
    health = c.get("/api/health").json()
    assert health["product"] == "业务窗关账"
    assert "modules" in health["meta"]
    h = _auth(c)
    assert (
        c.post(
            "/api/events",
            headers=h,
            json={
                "window_name": "W-1102",
                "biz_key": "A",
                "event_ts": "2026-11-02T11:00:00",
                "amount": 1,
            },
        ).json()["disposition"]
        == "窗内"
    )
    assert c.post("/api/windows/2/materialize", headers=h).status_code == 409
    assert c.post("/api/windows/2/close", headers=h).status_code == 200
    assert c.post("/api/windows/2/materialize", headers=h).status_code == 200
    assert c.get("/api/reconcile/2", headers=h).json()["aligned"] is True


def test_late_bucket_and_dashboard():
    c = TestClient(app)
    h = _auth(c)
    c.post("/api/windows/2/close", headers=h)
    r = c.post(
        "/api/events",
        headers=h,
        json={
            "window_name": "W-1102",
            "biz_key": "LATE-1",
            "event_ts": "2026-11-02T22:00:00",
            "amount": 4,
        },
    )
    assert r.json()["disposition"] == "迟到桶"
    late = c.get("/api/late-bucket", headers=h).json()
    assert late["count"] >= 1
    dash = c.get("/api/dashboard", headers=h).json()
    assert dash["late_bucket"] >= 1


def test_lock_contention():
    c = TestClient(app)
    h1 = _auth(c)
    tok2 = c.post(
        "/api/login", json={"username": "closer", "password": "close123"}
    ).json()["token"]
    h2 = {"Authorization": "Bearer " + tok2}
    assert c.post(
        "/api/locks/acquire", headers=h1, json={"lock_key": "window:99"}
    ).status_code == 200
    assert c.post(
        "/api/locks/acquire", headers=h2, json={"lock_key": "window:99"}
    ).status_code == 409
    cont = c.get("/api/contention", headers=h1).json()["items"]
    assert any(x["lock_key"] == "window:99" for x in cont)
