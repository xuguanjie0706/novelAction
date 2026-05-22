"""
Bootstrap Step 0 立项定位 — Pydantic 强校验与 normalize。

落库 / 注入 ctx 前必须通过本模型，避免缺字段导致下游 prompt 静默缺失全局约束。

v2 新增：
  - emotional_arc / pace_type 硬枚举校验（非法值强制降级为默认）
  - CONTRADICTORY_TROPE_PAIRS + detect_trope_conflicts() 爽点互斥检测
  - BootstrapPositioningCandidate 扩展模型（含读者评分 / positioning_type 等）
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ──────────────────────────────────────────────────────
# 枚举常量（供 validator 与外部校验共用）
# ──────────────────────────────────────────────────────

EMOTIONAL_ARC_VALUES: frozenset[str] = frozenset({"none", "low", "medium", "high"})
PACE_TYPE_VALUES: frozenset[str] = frozenset({"fast", "medium", "slow"})
POSITIONING_TYPE_VALUES: frozenset[str] = frozenset({"conservative", "differentiated", "niche"})

# ──────────────────────────────────────────────────────
# Trope 互斥对（检测到同时出现时标记冲突）
# 每个 frozenset 代表「不可共存」的一对关键词（模糊匹配，忽略大小写）
# ──────────────────────────────────────────────────────

CONTRADICTORY_TROPE_PAIRS: list[frozenset[str]] = [
    frozenset({"种田流", "无敌流"}),
    frozenset({"种田流", "爽文"}),
    frozenset({"慢热", "快节奏"}),
    frozenset({"苟道", "无敌流"}),
    frozenset({"低调种田", "高调打脸"}),
    frozenset({"治愈系", "无脑爽"}),
    frozenset({"深度世界观", "纯爽文"}),
]


def detect_trope_conflicts(tropes: list[str]) -> list[str]:
    """检测 tropes 列表中是否存在互斥组合。

    使用模糊关键词包含匹配（每个 trope 包含互斥对中的关键词即视为命中）。

    Args:
        tropes: 从 AI 输出中提取的爽点标签列表。

    Returns:
        冲突描述列表；空列表表示无冲突。
    """
    conflicts: list[str] = []
    lowered = [t.lower() for t in tropes]
    for pair in CONTRADICTORY_TROPE_PAIRS:
        items = list(pair)
        a, b = items[0], items[1]
        hit_a = any(a in t for t in lowered)
        hit_b = any(b in t for t in lowered)
        if hit_a and hit_b:
            conflicts.append(f'"{a}" 与 "{b}" 通常互斥，请确认是否兼容')
    return conflicts


# ──────────────────────────────────────────────────────
# 基础定位模型（扁平字段，与下游 ctx 消费契约一致）
# ──────────────────────────────────────────────────────

class BootstrapPositioning(BaseModel):
    """与 ``gen_positioning`` 提示词字段一一对应；缺项在 validate 阶段即失败。

    v2 变更：emotional_arc / pace_type 强制枚举校验；非法值降级为默认，不再抛出。
    """

    target_audience: str = Field(..., min_length=1, description="目标读者画像")
    tropes: list[str] = Field(default_factory=list, min_length=1, description="核心爽点类型")
    reference_works: list[str] = Field(default_factory=list, min_length=1)
    selling_point: str = Field(..., min_length=1, max_length=200)
    face_slap_pattern: str = Field(..., min_length=1, description="打脸节奏")
    emotional_arc: str = Field(default="low")
    pace_type: str = Field(default="medium")
    taboo_lines: list[str] = Field(default_factory=list, min_length=1)
    market_risk: str = Field(default="", max_length=500)
    differentiation_durability: str = Field(default="", max_length=500)
    # hook_test 保留兼容旧格式（原自评字段）；新格式中由 hook_text + reader_score 替代
    hook_test: str = Field(default="", max_length=500)

    @field_validator(
        "target_audience", "selling_point", "face_slap_pattern",
        "market_risk", "differentiation_durability", "hook_test",
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

    @field_validator("emotional_arc", mode="before")
    @classmethod
    def _validate_emotional_arc(cls, v: Any) -> str:
        """非法值降级为 'low'；不抛出，避免整个 positioning 因枚举值失败。"""
        s = str(v).strip().lower() if v is not None else ""
        return s if s in EMOTIONAL_ARC_VALUES else "low"

    @field_validator("pace_type", mode="before")
    @classmethod
    def _validate_pace_type(cls, v: Any) -> str:
        """非法值降级为 'medium'。"""
        s = str(v).strip().lower() if v is not None else ""
        return s if s in PACE_TYPE_VALUES else "medium"


# ──────────────────────────────────────────────────────
# 扩展候选方案模型（含读者评分 + 方案元信息）
# ──────────────────────────────────────────────────────

class BootstrapPositioningCandidate(BootstrapPositioning):
    """单个竞争定位方案；继承基础校验，追加 Step0 多方案流程字段。

    额外字段由两个 LLM 调用注入：
      - hook_text / positioning_type / expected_sign_rate / ceiling / risk_level：第一次（方案生成）
      - reader_score / reader_reason / click_trigger：第二次（读者模拟器）
    """

    name: str = Field(default="", description="方案名称，如「稳健套路向」")
    positioning_type: str = Field(default="conservative", description="conservative|differentiated|niche")
    hook_text: str = Field(default="", max_length=200, description="50字以内封面钩子（无自评分）")
    expected_sign_rate: str = Field(default="", description="预期签约率高/中高/中/低")
    ceiling: str = Field(default="", description="预期天花板描述")
    risk_level: str = Field(default="中", description="低/中/高")
    reader_score: int = Field(default=0, ge=0, le=10, description="读者模拟器评分 1-10")
    reader_reason: str = Field(default="", max_length=200, description="读者评分理由")
    click_trigger: str = Field(default="", max_length=100, description="最触发点击的关键词")

    @field_validator("positioning_type", mode="before")
    @classmethod
    def _validate_positioning_type(cls, v: Any) -> str:
        s = str(v).strip().lower() if v is not None else ""
        return s if s in POSITIONING_TYPE_VALUES else "conservative"

    @field_validator("reader_score", mode="before")
    @classmethod
    def _coerce_score(cls, v: Any) -> int:
        try:
            return max(0, min(10, int(v)))
        except (TypeError, ValueError):
            return 0

    @field_validator("name", "hook_text", "expected_sign_rate", "ceiling",
                     "risk_level", "reader_reason", "click_trigger", mode="before")
    @classmethod
    def _strip_candidate_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()


# ──────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────

def validate_and_dump_positioning(data: dict) -> dict:
    """校验并返回可 JSON 落库的 plain dict。

    Raises:
        pydantic.ValidationError: 字段缺失或类型不合法
    """
    return BootstrapPositioning.model_validate(data).model_dump()


def try_validate_positioning(data: dict) -> tuple[dict | None, str | None]:
    """软入口：成功返回 (dict, None)，失败返回 (None, 人类可读错误摘要)。"""
    try:
        return validate_and_dump_positioning(data), None
    except Exception as exc:  # noqa: BLE001 — 统一吞 ValidationError
        return None, str(exc)[:800]


def try_validate_candidate(data: dict) -> tuple[dict | None, str | None]:
    """校验单个候选方案（含扩展字段）；失败返回 (None, err)。"""
    try:
        return BootstrapPositioningCandidate.model_validate(data).model_dump(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:800]
