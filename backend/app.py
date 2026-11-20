"""业务窗关账 — FastAPI 入口（加厚母仓：多路由模块 + 锁/审计/空桩）。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from audit_svc import router as audit_router
from auth import router as auth_router
from db import FRONTEND, PRODUCT_META, init_db
from hold_svc import router as hold_router
from ingest_svc import router as ingest_router
from late_svc import router as late_router
from locks import router as locks_router
from materialize_svc import router as materialize_router
from reconcile_svc import router as reconcile_router
from reopen_svc import router as reopen_router
from windows_svc import router as windows_router

PRODUCT = "业务窗关账"
SKELETON = "事件按业务窗裁切，迟到进旁路或拒收，关窗后物化结果并与窗口对账"

app = FastAPI(title=PRODUCT, description=SKELETON)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth_router,
    windows_router,
    ingest_router,
    late_router,
    materialize_router,
    reconcile_router,
    locks_router,
    audit_router,
    hold_router,
    reopen_router,
):
    app.include_router(r)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    from db import DB_PATH, connect

    with connect() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM windows").fetchone()["c"]
        modules = conn.execute(
            "SELECT COUNT(*) c FROM sqlite_master WHERE type='table'"
        ).fetchone()["c"]
    return {
        "ok": True,
        "product": PRODUCT,
        "skeleton": SKELETON,
        "windows": n,
        "tables": modules,
        "db": str(DB_PATH),
        "meta": PRODUCT_META,
    }


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
