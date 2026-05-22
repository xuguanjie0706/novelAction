"""Bootstrap prompt 构造层。

把长 prompt 字面量（≥ 30 行）从 `generation_service.py` 抽出，按用途分文件：

- `blueprints`  — 世界设定卡蓝图常量与 prompt 片段、setting 默认 extra 补全。
- `word_budget` — 全书字数硬约束 prompt 片段。
- `project`     — Step 1：书名海选 + 结构化 premise + 结构化 world_overview prompt。

注：`single_shot.py` 已废弃（方案 B 已移除），保留空文件以避免 import 断裂。
"""

from .blueprints import (
    GEMINI_SETTING_BLUEPRINTS,
    SETTING_CARD_SCHEMA_BRIEF,
    CHARACTER_TARGET,
    FACTION_MIN_TARGET,
    FACTION_MAX_TARGET,
    SKILL_MIN_TARGET,
    SKILL_MAX_TARGET,
    ITEM_MIN_TARGET,
    ITEM_MAX_TARGET,
    setting_blueprints_for_prompt,
    setting_extra_with_defaults,
)
from .word_budget import book_length_constraints_for_prompt

__all__ = [
    "GEMINI_SETTING_BLUEPRINTS",
    "SETTING_CARD_SCHEMA_BRIEF",
    "CHARACTER_TARGET",
    "FACTION_MIN_TARGET",
    "FACTION_MAX_TARGET",
    "SKILL_MIN_TARGET",
    "SKILL_MAX_TARGET",
    "ITEM_MIN_TARGET",
    "ITEM_MAX_TARGET",
    "setting_blueprints_for_prompt",
    "setting_extra_with_defaults",
    "book_length_constraints_for_prompt",
]
