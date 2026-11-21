"""关窗后物化。

BUGFIX-15 修复：模拟失败按 ops/模拟失败清账卡.md 择定的**乙路径**执行——
只保留失败票，并在同一事务内抹掉先插入的成功行；抹除/失败票/审计任一步失败，
则回滚至成功行插入之前的保存点，成功行不留、失败票不留。禁止与甲路径混用。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from clearing_card import (
    CLEARING_CARD,
    ClearingDeviation,
    assert_path_b,
    record_deviation,
)
from db import connect, write_audit
from locks import release, require_lock
from models import MaterializeIn

router = APIRouter(tags=["materialize"])


@router.post("/api/windows/{wid}/materialize")
def materialize(
    wid: int,
    authorization: AuthHeader = None,
    body: MaterializeIn = MaterializeIn(),
):
    user = require_user(authorization)
    lock_key = f"materialize:{wid}"
    with connect() as conn:
        # 争用登记在 try_acquire 内独立提交；拿不到锁直接 409，不写任何业务
        require_lock(conn, lock_key, user)
        try:
            w = conn.execute("SELECT * FROM windows WHERE id=?", (wid,)).fetchone()
            if not w:
                raise HTTPException(404, "窗口不存在")
            if w["status"] != "已关闭":
                raise HTTPException(409, "未关窗不能物化")
            now = datetime.now().isoformat(timespec="seconds")
            rows = conn.execute(
                """SELECT COUNT(*) c, COALESCE(SUM(amount),0) s
                   FROM events WHERE window_id=? AND disposition='窗内'""",
                (wid,),
            ).fetchone()
            partition = body.partition_key or f"{w['name']}-g{w['generation']}"

            # 保存点划在成功行之前：失败分支无论走到哪一步出错，
            # 回滚都能把本次成功行一并抹掉，保证台账零成功行净增
            conn.execute("SAVEPOINT sp_mat")
            cur = conn.execute(
                """INSERT INTO materializations(window_id,status,row_count,total_amount,partition_key,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (wid, "成功", rows["c"], rows["s"], partition, now),
            )
            mat_id = cur.lastrowid

            if body.fail_simulate:
                _clear_failure_path_b(conn, user, wid, partition, now, rows, mat_id)

            conn.execute("RELEASE SAVEPOINT sp_mat")
            write_audit(
                conn,
                user,
                "materialize_ok",
                str(wid),
                {"row_count": rows["c"], "total_amount": rows["s"], "partition": partition},
            )
            conn.commit()
            return {
                "row_count": rows["c"],
                "total_amount": rows["s"],
                "partition_key": partition,
            }
        finally:
            release(conn, lock_key, user)
            conn.commit()


def _clear_failure_path_b(conn, user, wid, partition, now, rows, mat_id) -> None:
    """乙路径清账：同事务抹成功行 + 留失败票；任一步失败回滚至成功行插入前。"""
    # 卡面校验：只准乙路径。偏离即拒写，并记「清账偏了」。
    try:
        assert_path_b(CLEARING_CARD.path)
    except ClearingDeviation as exc:
        conn.execute("ROLLBACK TO SAVEPOINT sp_mat")
        record_deviation(conn, user, "materialize_path_deviation", f"清账偏了：{exc}")
        conn.commit()
        raise HTTPException(500, "清账偏了：偏离模拟失败清账卡，已拒写") from exc

    try:
        # 1) 同事务抹掉本次先插入的成功行 → 台账零成功行净增
        conn.execute("DELETE FROM materializations WHERE id=?", (mat_id,))
        # 2) 同事务只保留一张失败票，数据与被抹成功行同源
        conn.execute(
            """INSERT INTO failure_tickets(
                   window_id,status,row_count,total_amount,partition_key,
                   reason,related_mat_id,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                wid,
                "失败",
                rows["c"],
                rows["s"],
                partition,
                "模拟物化失败（fail_simulate）",
                mat_id,
                now,
            ),
        )
        ticket_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        # 3) 审计同事务登记，payload 与失败票挂钩
        write_audit(
            conn,
            user,
            "materialize_fail_sim",
            str(wid),
            {
                "partition": partition,
                "failure_ticket_id": ticket_id,
                "erased_mat_id": mat_id,
                "path": CLEARING_CARD.path,
            },
        )
    except Exception as exc:
        # 票或抹除失败：回滚至成功行插入前 —— 成功行不留、失败票不留、审计不留
        conn.execute("ROLLBACK TO SAVEPOINT sp_mat")
        record_deviation(
            conn,
            user,
            "materialize_clear_rollback",
            f"清账偏了：乙路径票/抹除失败，已整笔回滚: {exc!r}",
        )
        conn.commit()
        raise HTTPException(500, "模拟物化失败清账回滚（成功行与失败票均未留存）") from exc

    conn.execute("RELEASE SAVEPOINT sp_mat")
    # 清账结果（抹除+失败票+审计）随外层连接提交，确保同事务原子性
    conn.commit()
    raise HTTPException(500, "模拟物化失败（夹具用）：成功行已同事务抹除，仅留失败票")


@router.get("/api/materializations")
def list_mats(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT m.*, w.name AS window_name
               FROM materializations m
               JOIN windows w ON w.id=m.window_id
               ORDER BY m.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/failure-tickets")
def list_failure_tickets(authorization: AuthHeader = None):
    """失败票只读面：五处同态之「失败票」。"""
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.*, w.name AS window_name
               FROM failure_tickets t
               JOIN windows w ON w.id=t.window_id
               ORDER BY t.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/materializations/partition-stub")
def partition_stub(authorization: AuthHeader = None):
    """空桩模块：部分物化失败回滚策略待题面落地。"""
    user = require_user(authorization)
    with connect() as conn:
        write_audit(
            conn,
            user,
            "partition_mat_stub",
            None,
            {
                "paths": [
                    "整窗回滚",
                    "保留成功分区",
                ],
                "note": "正确性口径须择一，母仓不实现",
            },
        )
        conn.commit()
    return {"ok": True, "stub": True, "module": "partition_mat"}
