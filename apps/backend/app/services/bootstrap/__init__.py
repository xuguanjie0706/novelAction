"""Bootstrap 子包：一句话创意 → 全量小说初始化。

本包是 `services/generation_service.py` 的拆分目标位置（参见 CLAUDE.md「Service / Router 拆分蓝图」）。
本次（Step A）仅迁移 **模块级工具函数与 prompt 构造**；`GenerationService` 类与 14 个 `_gen_*` 步骤
仍保留在 `services/generation_service.py`，待后续 Step B / C 迁移。

外部 import 兼容性：所有原 `services/generation_service` 模块顶层符号（`_parse_json` /
`_safe_int` / `_coerce_power_system_rank` / `_sse` / `GEMINI_SETTING_BLUEPRINTS` /
`_setting_blueprints_for_prompt` / `_book_length_constraints_for_prompt` /
`_setting_extra_with_defaults` / `_single_shot_prompt` / `CHARACTER_TARGET` /
`FACTION_MIN_TARGET` / `FACTION_MAX_TARGET` / `SKILL_MIN_TARGET` / `SKILL_MAX_TARGET` /
`ITEM_MIN_TARGET` / `ITEM_MAX_TARGET`）由 `generation_service.py` 顶部 re-import 别名暴露，
任何老 `from app.services.generation_service import X` 写法都不受影响。
"""
