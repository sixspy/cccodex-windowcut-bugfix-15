"""迟到桶只读与处置空桩（题面可挖：拒收 vs 进桶、补入重算）。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth import AuthHeader, require_user
from db import connect, write_audit
from locks import release, require_lock

router = APIRouter(tags=["late"])


class LatePromoteIn(BaseModel):
    late_id: int
    target_window_name: str


@router.get("/api/late-bucket")
def list_late(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM late_bucket ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows], "count": len(rows)}


@router.get("/api/late-bucket/summary")
def late_summary(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM late_bucket"
        ).fetchone()
        by_window = conn.execute(
            """SELECT window_name, COUNT(*) c, COALESCE(SUM(amount),0) s
               FROM late_bucket GROUP BY window_name ORDER BY window_name"""
        ).fetchall()
        return {
            "count": row["c"],
            "amount": row["s"],
            "by_window": [dict(r) for r in by_window],
        }


@router.post("/api/late-bucket/promote-stub")
def promote_stub(body: LatePromoteIn, authorization: AuthHeader = None):
    """空桩：补入目标窗。题面实现须择一写路径，母仓仅登记意图。"""
    user = require_user(authorization)
    lock_key = f"late-promote:{body.late_id}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            late = conn.execute(
                "SELECT * FROM late_bucket WHERE id=?", (body.late_id,)
            ).fetchone()
            if not late:
                raise HTTPException(404, "迟到记录不存在")
            w = conn.execute(
                "SELECT * FROM windows WHERE name=?", (body.target_window_name,)
            ).fetchone()
            if not w:
                raise HTTPException(404, "目标窗口不存在")
            write_audit(
                conn,
                user,
                "late_promote_stub",
                str(body.late_id),
                {
                    "target": body.target_window_name,
                    "note": "空桩：未改正式窗内事件，待题面写路径落地",
                },
            )
            conn.commit()
            return {
                "ok": True,
                "stub": True,
                "message": "迟到补入空桩已登记，正式窗内事件未改",
            }
        finally:
            release(conn, lock_key, user)
            conn.commit()


@router.post("/api/late-bucket/{late_id}/discard-stub")
def discard_stub(late_id: int, authorization: AuthHeader = None):
    """空桩：作废迟到项（不删物理行，只审计）。"""
    user = require_user(authorization)
    with connect() as conn:
        late = conn.execute(
            "SELECT * FROM late_bucket WHERE id=?", (late_id,)
        ).fetchone()
        if not late:
            raise HTTPException(404, "迟到记录不存在")
        write_audit(
            conn,
            user,
            "late_discard_stub",
            str(late_id),
            {"biz_key": late["biz_key"], "at": datetime.now().isoformat(timespec="seconds")},
        )
        conn.commit()
    return {"ok": True, "stub": True}
