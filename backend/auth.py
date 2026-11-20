"""登录与会话。"""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from db import connect, sha_password, write_audit

SESSIONS: dict[str, str] = {}
router = APIRouter(tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


def require_user(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "未登录")
    token = authorization.removeprefix("Bearer ").strip()
    user = SESSIONS.get(token)
    if not user:
        raise HTTPException(401, "登录已失效")
    return user


AuthHeader = Annotated[str | None, Header()]


@router.post("/api/login")
def login(body: LoginIn):
    with connect() as conn:
        row = conn.execute(
            "SELECT username,role FROM users WHERE username=? AND password_sha=?",
            (body.username, sha_password(body.password)),
        ).fetchone()
        if not row:
            raise HTTPException(401, "账号或密码错误")
        token = secrets.token_hex(16)
        SESSIONS[token] = row["username"]
        write_audit(conn, row["username"], "login", "session", {"role": row["role"]})
        conn.commit()
    return {"token": token, "username": row["username"], "role": row["role"]}


@router.get("/api/me")
def me(authorization: str | None = Header(default=None)):
    user = require_user(authorization)
    with connect() as conn:
        row = conn.execute(
            "SELECT username,role FROM users WHERE username=?", (user,)
        ).fetchone()
    return dict(row) if row else {"username": user, "role": "未知"}
