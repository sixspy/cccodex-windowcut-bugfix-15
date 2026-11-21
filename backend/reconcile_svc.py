"""窗内事件与物化结果互证。

BUGFIX-15：结账灯只认真正提交的「成功」物化行；模拟失败抹掉的半截行不得充当
对齐素材（取消 tolerate_orphan_mat），并暴露失败票数，五处同态可核验。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect

router = APIRouter(tags=["reconcile"])


def _window_events(conn, wid: int):
    return conn.execute(
        """SELECT COUNT(*) c, COALESCE(SUM(amount),0) s
           FROM events WHERE window_id=? AND disposition='窗内'""",
        (wid,),
    ).fetchone()


def _latest_success_mat(conn, wid: int):
    # 只认成功行；失败票对应的被抹行已不存在，不会污染对齐
    return conn.execute(
        """SELECT * FROM materializations
           WHERE window_id=? AND status='成功'
           ORDER BY id DESC LIMIT 1""",
        (wid,),
    ).fetchone()


def _failure_ticket_count(conn, wid: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM failure_tickets WHERE window_id=?", (wid,)
    ).fetchone()["c"]


@router.get("/api/reconcile/{wid}")
def reconcile(wid: int, authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        w = conn.execute("SELECT * FROM windows WHERE id=?", (wid,)).fetchone()
        if not w:
            raise HTTPException(404, "窗口不存在")
        ev = _window_events(conn, wid)
        mat = _latest_success_mat(conn, wid)
        failure_tickets = _failure_ticket_count(conn, wid)
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
            "failure_tickets": failure_tickets,
            "late_bucket": late,
            "rejects": rejects,
            "aligned": aligned,
        }


@router.get("/api/reconcile")
def reconcile_all(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        windows = conn.execute("SELECT id,name,status FROM windows ORDER BY id").fetchall()
        items = []
        for w in windows:
            ev = _window_events(conn, w["id"])
            mat = _latest_success_mat(conn, w["id"])
            failure_tickets = _failure_ticket_count(conn, w["id"])
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
                    "failure_tickets": failure_tickets,
                    "late_bucket": late,
                }
            )
        return {"items": items}
