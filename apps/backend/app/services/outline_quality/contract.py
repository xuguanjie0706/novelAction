"""统一问题契约（IssueSet）。

动机：deterministic linter（LinterIssue）与 LLM 质检（outline_quality_check）
各产出不同形态的问题，三个消费者（生成回灌 / 门控 / 修复）需要同一套结构才能复用。
本模块定义归一化的 Issue / IssueSet / Directive，以及从 LinterReport 的适配器。

约束：纯数据结构 + 纯函数，无 DB、无 LLM 依赖；保持 <150 行。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

# 规则前缀 → 质量维度（用于按维度聚合、回灌时分组）
_PREFIX_TO_DIMENSION: dict[str, str] = {
    "CH": "chapter_craft",      # 单章工艺：钩子、核心事件、选择代价
    "SEQ": "continuity",        # 章际连贯：代价承接、去重
    "VB": "volume_beat",        # 卷级节拍：燃点、高潮呼应
    "RP": "reader_promise",     # 读者承诺兑现
    "CM": "core_mystery",       # 核心谜题推进
    "OC": "opening_contract",   # 开局追读承诺
    "GEN": "generation",        # 生成结构（批次漂移等）
}

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def dimension_for_rule(rule_id: str) -> str:
    """由规则 ID 前缀推导质量维度，未知前缀归 other。"""
    prefix = rule_id.split("-", 1)[0].upper() if rule_id else ""
    return _PREFIX_TO_DIMENSION.get(prefix, "other")


def issue_fingerprint(rule_id: str, field_name: str, chapter_number: int | None) -> str:
    """同一问题去重指纹：规则 + 字段 + 章号（卷内）。"""
    raw = f"{rule_id}|{field_name or ''}|{chapter_number if chapter_number is not None else ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class Issue:
    """归一化的单条问题，覆盖 linter 与 LLM 质检两个来源。"""

    rule_id: str
    severity: str  # critical | high | medium | low
    dimension: str
    message: str
    source: str = "linter"  # linter | qa_cheap | qa_holistic
    scope: str = "chapter"  # chapter | sequence | volume | book
    suggestion: str = ""
    field: str = ""
    chapter_number: int | None = None
    node_id: str | None = None
    auto_fixable: bool = False

    @property
    def fingerprint(self) -> str:
        return issue_fingerprint(self.rule_id, self.field, self.chapter_number)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "dimension": self.dimension,
            "message": self.message,
            "source": self.source,
            "scope": self.scope,
            "suggestion": self.suggestion,
            "field": self.field,
            "chapter_number": self.chapter_number,
            "node_id": self.node_id,
            "auto_fixable": self.auto_fixable,
            "fingerprint": self.fingerprint,
        }


@dataclass
class Directive:
    """给生成器的一条可执行约束（由高频问题转写而来）。"""

    dimension: str
    instruction: str
    severity: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "instruction": self.instruction, "severity": self.severity}


@dataclass
class IssueSet:
    """一次质检产出的归一化问题集合（按卷聚合）。"""

    volume_node_id: str | None = None
    issues: list[Issue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    def sorted_by_severity(self) -> list[Issue]:
        return sorted(self.issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 9))

    def by_dimension(self) -> dict[str, list[Issue]]:
        out: dict[str, list[Issue]] = {}
        for i in self.issues:
            out.setdefault(i.dimension, []).append(i)
        return out

    def rule_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for i in self.issues:
            counts[i.rule_id] = counts.get(i.rule_id, 0) + 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "volume_node_id": self.volume_node_id,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


def issue_set_from_linter_report(report: Any, volume_node_id: str | None = None) -> IssueSet:
    """LinterReport → IssueSet 适配器。

    Args:
        report: services.outline_linter.schemas.LinterReport（鸭子类型，取 .issues）。
        volume_node_id: 归属卷节点 ID。
    """
    issues: list[Issue] = []
    for li in getattr(report, "issues", []) or []:
        issues.append(
            Issue(
                rule_id=li.rule_id,
                severity=li.severity,
                dimension=dimension_for_rule(li.rule_id),
                message=li.message,
                source="linter",
                scope=li.scope,
                suggestion=getattr(li, "suggestion", "") or "",
                field=getattr(li, "field", "") or "",
                chapter_number=getattr(li, "chapter_number_in_volume", None),
                node_id=getattr(li, "node_id", None),
                auto_fixable=bool(getattr(li, "auto_fixable", False)),
            )
        )
    return IssueSet(volume_node_id=volume_node_id, issues=issues)
