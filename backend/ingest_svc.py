"""事件入账：窗内 / 拒收 / 迟到桶分流。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect, write_audit
from locks import release, require_lock
from models import EventIn

router = APIRouter(tags=["ingest"])


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@router.post("/api/events")
def ingest_event(body: EventIn, authorization: AuthHeader = None):
    user = require_user(authorization)
    lock_key = f"ingest:{body.window_name}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            w = conn.execute(
                "SELECT * FROM windows WHERE name=?", (body.window_name,)
            ).fetchone()
            if not w:
                raise HTTPException(404, "窗口不存在")
            ts = body.event_ts
            created = _now()
            if w["status"] == "已关闭":
                cur = conn.execute(
                    """INSERT INTO events(window_id,biz_key,event_ts,amount,disposition,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (None, body.biz_key, ts, body.amount, "迟到桶", created),
                )
                eid = cur.lastrowid
                conn.execute(
                    """INSERT INTO late_bucket(event_id,window_name,biz_key,event_ts,amount,reason,created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        eid,
                        body.window_name,
                        body.biz_key,
                        ts,
                        body.amount,
                        "关窗后到达",
                        created,
                    ),
                )
                write_audit(
                    conn,
                    user,
                    "ingest_late",
                    body.biz_key,
                    {"window": body.window_name},
                )
                conn.commit()
                return {"disposition": "迟到桶", "event_id": eid}

            if not (w["open_at"] <= ts <= w["close_at"]):
                conn.execute(
                    """INSERT INTO events(window_id,biz_key,event_ts,amount,disposition,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (None, body.biz_key, ts, body.amount, "拒收", created),
                )
                conn.execute(
                    """INSERT INTO reject_slips(window_name,biz_key,event_ts,amount,reason,created_at)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        body.window_name,
                        body.biz_key,
                        ts,
                        body.amount,
                        "窗外且窗仍开启",
                        created,
                    ),
                )
                write_audit(
                    conn,
                    user,
                    "ingest_reject",
                    body.biz_key,
                    {"window": body.window_name},
                )
                conn.commit()
                raise HTTPException(409, "事件时间落在窗外且窗仍开启：拒收")

            cur = conn.execute(
                """INSERT INTO events(window_id,biz_key,event_ts,amount,disposition,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (w["id"], body.biz_key, ts, body.amount, "窗内", created),
            )
            write_audit(
                conn,
                user,
                "ingest_in_window",
                body.biz_key,
                {"window_id": w["id"]},
            )
            conn.commit()
            return {"disposition": "窗内", "window_id": w["id"], "event_id": cur.lastrowid}
        finally:
            release(conn, lock_key, user)
            conn.commit()


@router.get("/api/events")
def list_events(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT 200"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.get("/api/rejects")
def list_rejects(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM reject_slips ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return {"items": [dict(r) for r in rows]}
