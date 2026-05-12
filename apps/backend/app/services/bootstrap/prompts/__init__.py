"""Bootstrap prompt 构造层。

把长 prompt 字面量（≥ 30 行）从 `generation_service.py` 抽出，按用途分文件：

- `blueprints` — 世界设定卡蓝图常量与 prompt 片段、setting 默认 extra 补全。
- `word_budget` — 全书字数硬约束 prompt 片段。
- `single_shot` — 方案 B 单次全量生成 prompt（最长，~90 行）。

向后兼容：旧名（`GEMINI_SETTING_BLUEPRINTS` / `_SETTING_CARD_SCHEMA_BRIEF` /
`CHARACTER_TARGET` / `FACTION_*` / `SKILL_*` / `ITEM_*` /
`_setting_blueprints_for_prompt` / `_book_length_constraints_for_prompt` /
`_setting_extra_with_defaults` / `_single_shot_prompt`）由
`services/generation_service.py` 顶部 re-import 暴露。
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
from .single_shot import single_shot_prompt

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
    "single_shot_prompt",
]
