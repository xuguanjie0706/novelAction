"""大纲质量闭环：统一问题契约 + 问题台账 + 生成期回灌。

设计锚点见仓库根 `大纲生成-检查-修复闭环设计-v1.0.md`。
核心理念：一个评分器，三个消费者（生成/门控/修复），一个收敛循环。
本包只承载「契约 + 台账 + 回灌」基础设施，不直连 LLM、不写编排逻辑。
"""

from app.services.outline_quality.contract import (
    Directive,
    Issue,
    IssueSet,
    issue_fingerprint,
    issue_set_from_linter_report,
)

__all__ = [
    "Directive",
    "Issue",
    "IssueSet",
    "issue_fingerprint",
    "issue_set_from_linter_report",
]
