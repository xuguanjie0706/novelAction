"""
番茄 Bootstrap Step 0 立项定位 — 与 gen_algo_positioning 输出字段一致。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class BootstrapFanqiePositioning(BaseModel):
    """番茄算法立项会议产物（gate 审阅 / resume approve 用）。"""

    genre_archetype: str = Field(..., min_length=1)
    core_satisfaction: str = Field(..., min_length=1)
    competitor_works: list[str] = Field(default_factory=list, min_length=1)
    differentiation: str = Field(default="", max_length=500)
    platform_tags: list[str] = Field(default_factory=list, min_length=1)
    algo_hook: str = Field(..., min_length=1)
    completion_rate_prediction: str = Field(default="", max_length=200)
    taboo_check: str = Field(default="", max_length=200)

    @field_validator(
        "genre_archetype", "core_satisfaction", "differentiation",
        "algo_hook", "completion_rate_prediction", "taboo_check",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("competitor_works", "platform_tags", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            s = str(v).strip()
            return [s] if s else []
        out: list[str] = []
        for x in v:
            s = str(x).strip() if not isinstance(x, str) else x.strip()
            if s:
                out.append(s)
        return out


def try_validate_fanqie_positioning(data: dict) -> tuple[dict | None, str | None]:
    """成功返回 (dict, None)，失败返回 (None, 错误摘要)。"""
    try:
        return BootstrapFanqiePositioning.model_validate(data).model_dump(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:800]
