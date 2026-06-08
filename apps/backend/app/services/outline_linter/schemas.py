"""Linter 输出结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


LINTER_VERSION = "1.2.1"


@dataclass
class LinterIssue:
    rule_id: str
    severity: str  # critical | high | medium | low
    scope: str  # chapter | sequence | volume
    message: str
    suggestion: str = ""
    field: str = ""
    chapter_number_in_volume: int | None = None
    node_id: str | None = None
    auto_fixable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "scope": self.scope,
            "message": self.message,
            "suggestion": self.suggestion,
            "field": self.field,
            "chapter_number_in_volume": self.chapter_number_in_volume,
            "node_id": self.node_id,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class LinterReport:
    linter_version: str = LINTER_VERSION
    status: str = "ok"  # ok | warn | failed
    issues: list[LinterIssue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    def to_dict(self) -> dict[str, Any]:
        return {
            "linter_version": self.linter_version,
            "status": self.status,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }

    def finalize_status(self) -> None:
        if self.critical_count > 0 or self.high_count >= 3:
            self.status = "failed"
        elif self.issues:
            self.status = "warn"
        else:
            self.status = "ok"
