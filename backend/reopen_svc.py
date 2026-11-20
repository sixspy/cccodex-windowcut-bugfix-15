"""窗重开空桩：作废重算 vs 增量补丁合并。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from auth import AuthHeader, require_user
from db import connect, write_audit
from locks import release, require_lock
from models import ReopenIn

router = APIRouter(tags=["reopen"])


@router.get("/api/reopen-ledger")
def list_reopen(authorization: AuthHeader = None):
    require_user(authorization)
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.*, w.name AS window_name
               FROM reopen_ledger r
               JOIN windows w ON w.id=r.window_id
               ORDER BY r.id DESC"""
        ).fetchall()
        return {"items": [dict(r) for r in rows]}


@router.post("/api/windows/{wid}/reopen-stub")
def reopen_stub(wid: int, body: ReopenIn, authorization: AuthHeader = None):
    user = require_user(authorization)
    lock_key = f"reopen:{wid}"
    with connect() as conn:
        require_lock(conn, lock_key, user)
        try:
            w = conn.execute("SELECT * FROM windows WHERE id=?", (wid,)).fetchone()
            if not w:
                raise HTTPException(404, "窗口不存在")
            if w["status"] != "已关闭":
                raise HTTPException(409, "仅已关闭窗可登记重开空桩")
            if body.mode not in ("作废重算", "增量补丁"):
                raise HTTPException(400, "mode 须为作废重算或增量补丁")
            now = datetime.now().isoformat(timespec="seconds")
            to_gen = int(w["generation"]) + 1
            conn.execute(
                """INSERT INTO reopen_ledger(window_id,from_generation,to_generation,mode,status,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (wid, w["generation"], to_gen, body.mode, "空桩登记", now),
            )
            write_audit(
                conn,
                user,
                "reopen_stub",
                str(wid),
                {
                    "mode": body.mode,
                    "from_generation": w["generation"],
                    "to_generation": to_gen,
                    "note": "未改窗口 status/generation，待题面写路径",
                },
            )
            conn.commit()
            return {
                "ok": True,
                "stub": True,
                "mode": body.mode,
                "from_generation": w["generation"],
                "to_generation": to_gen,
            }
        finally:
            release(conn, lock_key, user)
            conn.commit()
