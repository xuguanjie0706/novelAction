"""
Bootstrap Step 0 立项定位 — Pydantic 强校验与 normalize。

落库 / 注入 ctx 前必须通过本模型，避免缺字段导致下游 prompt 静默缺失全局约束。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class BootstrapPositioning(BaseModel):
    """与 ``gen_positioning`` 提示词字段一一对应；缺项在 validate 阶段即失败。"""

    target_audience: str = Field(..., min_length=1, description="目标读者画像")
    tropes: list[str] = Field(default_factory=list, min_length=1, description="核心爽点类型")
    reference_works: list[str] = Field(default_factory=list, min_length=1)
    selling_point: str = Field(..., min_length=1, max_length=200)
    face_slap_pattern: str = Field(..., min_length=1, description="打脸节奏")
    emotional_arc: str = Field(..., min_length=1)
    pace_type: str = Field(..., min_length=1)
    taboo_lines: list[str] = Field(default_factory=list, min_length=1)
    market_risk: str = Field(default="", max_length=500)
    differentiation_durability: str = Field(default="", max_length=500)
    hook_test: str = Field(default="", max_length=500)

    @field_validator(
        "target_audience", "selling_point", "face_slap_pattern",
        "emotional_arc", "pace_type", "market_risk",
        "differentiation_durability", "hook_test",
        mode="before",
    )
    @classmethod
    def _strip_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("tropes", "reference_works", "taboo_lines", mode="before")
    @classmethod
    def _coerce_str_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return [str(v).strip()] if str(v).strip() else []
        out: list[str] = []
        for x in v:
            if x is None:
                continue
            s = str(x).strip() if not isinstance(x, str) else x.strip()
            if s:
                out.append(s)
        return out


def validate_and_dump_positioning(data: dict) -> dict:
    """
    校验并返回可 JSON 落库的 plain dict。

    Raises:
        pydantic.ValidationError: 字段缺失或类型不合法
    """
    return BootstrapPositioning.model_validate(data).model_dump()


def try_validate_positioning(data: dict) -> tuple[dict | None, str | None]:
    """
    软入口：成功返回 (dict, None)，失败返回 (None, 人类可读错误摘要)。
    """
    try:
        return validate_and_dump_positioning(data), None
    except Exception as exc:  # noqa: BLE001 — 统一吞 ValidationError
        return None, str(exc)[:800]
