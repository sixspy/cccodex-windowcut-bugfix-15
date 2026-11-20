"""窗内事件与物化结果互证。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect

router = APIRouter(tags=["reconcile"])


@router.get("/api/reconcile/{wid}")
def reconcile(wid: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        w = conn.execute("SELECT * FROM windows WHERE id=?", (wid,)).fetchone()
        if not w:
            raise HTTPException(404, "窗口不存在")
        ev = conn.execute(
            """SELECT COUNT(*) c, COALESCE(SUM(amount),0) s
               FROM events WHERE window_id=? AND disposition='窗内'""",
            (wid,),
        ).fetchone()
        mat = conn.execute(
            "SELECT * FROM materializations WHERE window_id=? ORDER BY id DESC LIMIT 1",
            (wid,),
        ).fetchone()
        late = conn.execute(
            "SELECT COUNT(*) c FROM late_bucket WHERE window_name=?",
            (w["name"],),
        ).fetchone()["c"]
        rejects = conn.execute(
            "SELECT COUNT(*) c FROM reject_slips WHERE window_name=?",
            (w["name"],),
        ).fetchone()["c"]
        aligned = (
            bool(mat)
            and mat["row_count"] == ev["c"]
            and abs(mat["total_amount"] - ev["s"]) < 1e-6
        )
        return {
            "window": dict(w),
            "window_events": ev["c"],
            "window_amount": ev["s"],
            "materialized": dict(mat) if mat else None,
            "late_bucket": late,
            "rejects": rejects,
            "aligned": aligned,
            # BUGFIX-15 埋雷：半截成功行仍可被当成对齐素材
            "tolerate_orphan_mat": True,
        }


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        windows = conn.execute("SELECT id,name,status FROM windows ORDER BY id").fetchall()
        items = []
        for w in windows:
            ev = conn.execute(
                """SELECT COUNT(*) c, COALESCE(SUM(amount),0) s
                   FROM events WHERE window_id=? AND disposition='窗内'""",
                (w["id"],),
            ).fetchone()
            mat = conn.execute(
                "SELECT * FROM materializations WHERE window_id=? ORDER BY id DESC LIMIT 1",
                (w["id"],),
            ).fetchone()
            late = conn.execute(
                "SELECT COUNT(*) c FROM late_bucket WHERE window_name=?",
                (w["name"],),
            ).fetchone()["c"]
            aligned = (
                bool(mat)
                and mat["row_count"] == ev["c"]
                and abs(mat["total_amount"] - ev["s"]) < 1e-6
            )
            items.append(
                {
                    "window_id": w["id"],
                    "name": w["name"],
                    "status": w["status"],
                    "aligned": aligned,
                    "window_events": ev["c"],
                    "late_bucket": late,
                }
            )
        return {"items": items}
