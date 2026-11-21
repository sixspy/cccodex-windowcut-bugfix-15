"""模拟失败清账卡（代码锚点）。

与 ops/模拟失败清账卡.md 同源：2026-11-21 择定乙路径，当日禁止改口。
materialize_svc 的失败分支只允许按本卡口径写；偏离一律拒写并记「清账偏了」。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter

from auth import AuthHeader, require_user
from db import connect

router = APIRouter(tags=["clearing_card"])

# 卡面常量：唯一口径。甲路径被否决，禁止在代码里另开分支混用。
PATH_B = "乙"
PATH_A = "甲"
CHOSEN_PATH = PATH_B
FROZEN_DATE = "2026-11-21"
CARD_TITLE = "模拟失败清账卡"


@dataclass(frozen=True)
class ClearingCard:
    title: str
    path: str
    frozen_date: str
    rule: str
    rejected_path: str


CLEARING_CARD = ClearingCard(
    title=CARD_TITLE,
    path=CHOSEN_PATH,
    frozen_date=FROZEN_DATE,
    rule=(
        "只保留失败票，并在同一事务内抹掉成功行；"
        "失败票写入或抹除任一步失败，则票与抹除整体回滚"
    ),
    rejected_path=PATH_A,
)


def card_snapshot() -> dict:
    """只读卡面，供接口核验，禁止返回可变对象。"""
    return {
        "title": CLEARING_CARD.title,
        "chosen_path": CLEARING_CARD.path,
        "rejected_path": CLEARING_CARD.rejected_path,
        "frozen_date": CLEARING_CARD.frozen_date,
        "rule": CLEARING_CARD.rule,
        "locked": True,
    }


def assert_path_b(attempted_path: str) -> None:
    """偏离清账卡即拒写。调用方须在外层事务内，随后回滚。"""
    if attempted_path != CLEARING_CARD.path:
        raise ClearingDeviation(
            f"偏离模拟失败清账卡：仅允许乙路径，收到 {attempted_path!r}"
        )


class ClearingDeviation(Exception):
    """清账偏了：口径混用/偏离，触发拒写。"""


def record_deviation(conn, actor: str, action: str, detail: str) -> None:
    """在当前事务内登记「清账偏了」；随调用方事务一起提交或回滚。"""
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO clearing_deviation(actor,action,detail,created_at)
           VALUES (?,?,?,?)""",
        (actor, action, detail, now),
    )


def list_deviations() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clearing_deviation ORDER BY id DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/api/clearing-card")
def get_clearing_card(authorization: AuthHeader = None):
    """只读卡面：当日冻结口径，供页面/测试核验。"""
    require_user(authorization)
    return card_snapshot()


@router.get("/api/clearing-deviations")
def get_deviations(authorization: AuthHeader = None):
    """清账偏了登记面：偏离卡面的拒写记录。"""
    require_user(authorization)
    return {"items": list_deviations()}
