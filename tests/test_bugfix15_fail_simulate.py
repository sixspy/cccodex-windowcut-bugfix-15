"""BUGFIX-15 失败测：
1) 模拟失败留账失败测 —— fail_simulate 报 500 后台账零成功行净增、失败票同态；
2) 真假物化对撞争用失败测 —— 同窗并发物化，后到者只记争用不写业务。

两个测试先于修复落地，必须先红，修复后转绿。口径见 ops/模拟失败清账卡.md（乙路径）。
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app import app, init_db


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setattr("db.DB_PATH", tmp_path / "bugfix15.db")
    init_db()
    yield


def _auth(c: TestClient, username="admin", password="123456") -> dict:
    tok = c.post(
        "/api/login", json={"username": username, "password": password}
    ).json()["token"]
    return {"Authorization": "Bearer " + tok}


def _counts(conn, wid: int) -> tuple[int, int]:
    success = conn.execute(
        "SELECT COUNT(*) c FROM materializations WHERE window_id=? AND status='成功'",
        (wid,),
    ).fetchone()["c"]
    tickets = conn.execute(
        "SELECT COUNT(*) c FROM failure_tickets WHERE window_id=?", (wid,)
    ).fetchone()["c"]
    return success, tickets


def test_fail_simulate_leaves_no_success_row_but_failure_ticket():
    """红测 1：模拟失败必须不留成功行，只留失败票（乙路径五处同态）。"""
    c = TestClient(app)
    h = _auth(c)
    import db

    with db.connect() as conn:
        success_before, tickets_before = _counts(conn, 1)

    r = c.post(
        "/api/windows/1/materialize", headers=h, json={"fail_simulate": True}
    )
    # 报错语义保持
    assert r.status_code == 500
    assert "模拟物化失败" in r.json()["detail"]

    with db.connect() as conn:
        success_after, tickets_after = _counts(conn, 1)

    # 台账：零成功行净增（先插的成功行须同事务抹除）
    assert success_after == success_before, "失败后仍残留成功物化行，半截污染"
    # 失败票：恰好新增一张，且与被抹成功行同源
    assert tickets_after == tickets_before + 1
    with db.connect() as conn:
        ticket = conn.execute(
            """SELECT * FROM failure_tickets WHERE window_id=1
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    assert ticket["status"] == "失败"
    assert ticket["partition_key"] == "W-1101-g1"
    assert ticket["row_count"] == 1
    assert abs(ticket["total_amount"] - 12.5) < 1e-6

    # 结账灯：不得把被抹行当对齐素材；暴露失败票数
    recon = c.get("/api/reconcile/1", headers=h).json()
    assert "tolerate_orphan_mat" not in recon
    assert recon["failure_tickets"] == tickets_after
    assert recon["aligned"] is True  # 种子成功行仍在，对齐不被失败票污染

    # 审计：有且仅有一次模拟失败审计
    audits = c.get("/api/audit?limit=50", headers=h).json()["items"]
    fail_audits = [a for a in audits if a["action"] == "materialize_fail_sim"]
    assert len(fail_audits) == 1
    assert fail_audits[0]["target"] == "1"

    # 争用面：正常持锁不记争用
    contention = c.get("/api/contention", headers=h).json()["items"]
    assert not any(x["lock_key"] == "materialize:1" for x in contention)

    # 再次模拟失败：仍零成功行净增、失败票再增一张（幂等口径稳定）
    r2 = c.post(
        "/api/windows/1/materialize", headers=h, json={"fail_simulate": True}
    )
    assert r2.status_code == 500
    with db.connect() as conn:
        success_final, tickets_final = _counts(conn, 1)
    assert success_final == success_before
    assert tickets_final == tickets_before + 2


def test_true_and_false_materialize_contend_on_same_lock():
    """红测 2：两人同窗一真一假对撞，后到只记争用（409），不写任何业务数据。"""
    c = TestClient(app)
    h1 = _auth(c)
    h2 = _auth(c, "closer", "close123")
    import db

    results: dict[str, int] = {}

    def fake_materialize():
        r = c.post(
            "/api/windows/1/materialize",
            headers=h1,
            json={"fail_simulate": True},
        )
        results["fake"] = r.status_code

    # 在锁表里预置 h1 持锁，等价于先到的假物化已进入临界区且尚未退出
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO window_locks(lock_key,holder,acquired_at) VALUES (?,?,?)",
            ("materialize:1", "admin", "2026-11-21T10:00:00"),
        )
        conn.commit()

    # 后到的真物化必须争用失败（此时锁仍被 admin 持有）
    r_true = c.post(
        "/api/windows/1/materialize", headers=h2, json={"fail_simulate": False}
    )
    results["true"] = r_true.status_code
    assert results["true"] == 409
    assert "争用" in r_true.json()["detail"]

    # 争用面同态（不依赖新增表）：恰好一条 materialize:1 争用，后到者是 closer
    contention = c.get("/api/contention", headers=h1).json()["items"]
    mat_contention = [x for x in contention if x["lock_key"] == "materialize:1"]
    assert len(mat_contention) == 1
    assert mat_contention[0]["actor"] == "closer"
    assert mat_contention[0]["action"] == "争用"

    # 后到者一笔业务都没写：争用期间台账成功行数不变（仍只有种子行）
    with db.connect() as conn:
        success_during = conn.execute(
            "SELECT COUNT(*) c FROM materializations WHERE window_id=1 AND status='成功'"
        ).fetchone()["c"]
    assert success_during == 1

    # 释放预置锁后，先到者的假物化再走乙路径（同票同抹除口径）
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM window_locks WHERE lock_key='materialize:1'"
        )
        conn.commit()
    t = threading.Thread(target=fake_materialize)
    t.start()
    t.join(timeout=5)
    assert results["fake"] == 500

    with db.connect() as conn:
        success_n, ticket_n = _counts(conn, 1)

    # 后到者一笔业务都没写：台账仍只有种子行，失败票只来自持锁者那一笔
    assert success_n == 1
    assert ticket_n == 1

    # 锁最终被持锁者释放
    with db.connect() as conn:
        left = conn.execute(
            "SELECT COUNT(*) c FROM window_locks WHERE lock_key='materialize:1'"
        ).fetchone()["c"]
    assert left == 0
