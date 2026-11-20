"""请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EventIn(BaseModel):
    window_name: str
    biz_key: str
    event_ts: str
    amount: float = Field(gt=-1e12)


class WindowCreateIn(BaseModel):
    name: str
    open_at: str
    close_at: str


class HoldIn(BaseModel):
    window_name: str
    biz_key: str
    event_ts: str
    amount: float


class ReopenIn(BaseModel):
    mode: str = "作废重算"  # 或「增量补丁」——题面择一后落地，母仓仅空桩登记


class MaterializeIn(BaseModel):
    partition_key: str | None = None
    fail_simulate: bool = False
