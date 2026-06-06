"""修仙直白线 Step 0 立项定位 — 与 gen_xianxia_positioning 输出字段一致。

修仙立项以「数值爬升」为引擎，字段与番茄打脸框架不同，故独立 schema：
subgenre / core_satisfaction 必填，其余可空（gate 审阅 / resume approve 用）。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class BootstrapXianxiaPositioning(BaseModel):
    """修仙立项会议产物。"""

    subgenre: str = Field(..., min_length=1)
    core_satisfaction: str = Field(..., min_length=1)
    progression_fantasy: str = Field(default="", max_length=500)
    tension_source: str = Field(default="", max_length=500)
    opening_fortune: str = Field(default="", max_length=500)
    power_fantasy_curve: str = Field(default="", max_length=300)
    reader_tags: list[str] = Field(default_factory=list)
    completion_hook: str = Field(default="", max_length=300)
    taboo_check: str = Field(default="", max_length=200)

    @field_validator(
        "subgenre", "core_satisfaction", "progression_fantasy", "tension_source",
        "opening_fortune", "power_fantasy_curve", "completion_hook", "taboo_check",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("reader_tags", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            s = str(v).strip()
            return [s] if s else []
        out: list[str] = []
        for x in v:
            s = x.strip() if isinstance(x, str) else str(x).strip()
            if s:
                out.append(s)
        return out


def try_validate_xianxia_positioning(data: dict) -> tuple[dict | None, str | None]:
    """成功返回 (dict, None)，失败返回 (None, 错误摘要)。"""
    try:
        return BootstrapXianxiaPositioning.model_validate(data).model_dump(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:800]
