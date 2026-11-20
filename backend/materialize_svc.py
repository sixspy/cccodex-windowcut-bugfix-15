"""关窗后物化。空桩预留：分区失败回滚 vs 保留成功分区。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
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
            # BUGFIX-15 埋雷：先插成功行再模拟失败，留下半截台账
            conn.execute(
                """INSERT INTO materializations(window_id,status,row_count,total_amount,partition_key,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (wid, "成功", rows["c"], rows["s"], partition, now),
            )
            conn.commit()
            if body.fail_simulate:
                write_audit(
                    conn,
                    user,
                    "materialize_fail_sim",
                    str(wid),
                    {"partition": partition, "bug": "success_left"},
                )
                conn.commit()
                raise HTTPException(500, "模拟物化失败（夹具用）")
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
