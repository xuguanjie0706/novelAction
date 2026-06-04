"""同人 Bootstrap Step 0 立项定位 — 与 gen_fanfic_positioning 输出字段一致。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FanficTrope = Literal["transmigration", "rebirth", "au"]
CanonFidelity = Literal["strict", "medium", "loose"]


class BootstrapFanficPositioning(BaseModel):
    """同人·番茄立项会议产物（gate 审阅 / resume approve 用）。"""

    source_work_title: str = Field(..., min_length=1)
    fanfic_trope: FanficTrope
    fanfic_trope_label: str = Field(..., min_length=1)
    core_satisfaction: str = Field(..., min_length=1)
    fan_expectation: str = Field(..., min_length=1)
    canon_fidelity: CanonFidelity = "medium"
    platform_tags: list[str] = Field(default_factory=list, min_length=1)
    algo_hook: str = Field(..., min_length=1)
    ooc_taboos: list[str] = Field(default_factory=list)
    differentiation: str = Field(default="", max_length=500)
    taboo_check: str = Field(default="", max_length=200)

    @field_validator(
        "source_work_title", "fanfic_trope_label", "core_satisfaction",
        "fan_expectation", "differentiation", "algo_hook", "taboo_check",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("platform_tags", "ooc_taboos", mode="before")
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


def try_validate_fanfic_positioning(data: dict) -> tuple[dict | None, str | None]:
    """成功返回 (dict, None)，失败返回 (None, 错误摘要)。"""
    try:
        return BootstrapFanficPositioning.model_validate(data).model_dump(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:800]
