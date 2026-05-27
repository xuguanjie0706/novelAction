_ALLOWED_CHARACTER_STATUS = {"alive", "dead", "missing", "sealed", "transformed"}
_ALLOWED_STORYLINE_STATUS = {"planned", "active", "climax", "resolved", "dropped"}
_QUALITY_DEBT_TYPES = {
    "character",
    "character_state",
    "character_location",
    "continuity",
    "continuity_gap",
    "foreshadow",
    "hook_continuity",
    "hooks",
    "outline_alignment",
    "plot",
    "setting",
    "setting_consistency",
    "power_system",
    "storyline_drift",
    "storyline_crossover",
    "storyline_screen_time",
    "storyline_neglect",
}
_QUALITY_DEBT_SEVERITIES = {"critical", "high", "medium"}

_SETTING_CORE_LABELS = [
    ("core_concept", "一句话核心"),
    ("genre_position", "类型定位"),
    ("protagonist_drive", "主角驱动力"),
    ("core_conflict", "核心矛盾"),
    ("reader_hook", "追读钩子"),
    ("emotional_tone", "情感基调"),
    ("boundaries", "禁忌边界"),
    ("ending_direction", "结局倾向"),
]

_SETTING_FOCUS_LABELS = [
    ("summary", "核心摘要"),
    ("story_function", "故事作用"),
    ("conflict_seed", "冲突种子"),
    ("cost_or_risk", "代价/风险"),
    ("affected_people", "影响对象"),
    ("exception_or_loophole", "例外/漏洞"),
    ("visual_anchor", "画面锚点"),
]

_MAX_COHERENCE_APPLY_CHAPTERS = 12
