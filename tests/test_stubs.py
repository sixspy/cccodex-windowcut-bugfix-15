"""空桩与旁路面冒烟：证明模块文件存在且接口可登记。"""
from fastapi.testclient import TestClient

from app import app, init_db
import pytest


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "stub.db")
    init_db()
    yield


def _auth(c):
    tok = c.post(
        "/api/login", json={"username": "admin", "password": "123456"}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def test_hold_and_reopen_stubs():
    c = TestClient(app)
    h = _auth(c)
    r = c.post(
        "/api/holds",
        headers=h,
        json={
            "window_name": "W-1102",
            "biz_key": "H1",
            "event_ts": "2026-11-02T15:00:00",
            "amount": 1.5,
        },
    )
    assert r.status_code == 200
    hid = r.json()["hold_id"]
    assert c.post(f"/api/holds/{hid}/release-stub", headers=h).json()["stub"] is True
    c.post("/api/windows/2/close", headers=h)
    stub = c.post(
        "/api/windows/2/reopen-stub", headers=h, json={"mode": "增量补丁"}
    ).json()
    assert stub["stub"] is True
    assert stub["mode"] == "增量补丁"
    assert c.get("/api/reopen-ledger", headers=h).json()["items"]


def test_reject_outside_open_window():
    c = TestClient(app)
    h = _auth(c)
    r = c.post(
        "/api/events",
        headers=h,
        json={
            "window_name": "W-1102",
            "biz_key": "OUT",
            "event_ts": "2026-10-01T00:00:00",
            "amount": 9,
        },
    )
    assert r.status_code == 409
    rejects = c.get("/api/rejects", headers=h).json()["items"]
    assert any(x["biz_key"] == "OUT" for x in rejects)
