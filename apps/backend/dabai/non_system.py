"""非系统文（法器流 / 魔道修仙）检测与 prompt 块。

当 logline 或 positioning.taboo_lines 标明不要系统 UI 时，Bootstrap 各步
自动切换为「血炼魔器 / 魔经残篇」口径，禁止生成叮、面板、任务栏类设定。
"""

from __future__ import annotations

# logline / taboo 命中 → 走法器流
_ARTIFACT_MARKERS = (
    "不要系统", "无系统", "非系统", "不写系统", "禁止系统", "不要系统文",
    "无系统面板", "不要系统面板", "无叮", "禁止叮",
    "法器", "魔器", "魂幡", "魔幡", "万魂幡", "血炼", "魔经", "魔门", "魔道",
    "普通修仙", "黑暗修仙", "血祭", "代修",
)

# 明确系统流 → 不触发法器约束
_SYSTEM_MARKERS = ("系统流", "签到系统", "属性面板", "万物吞噬系统", "觉醒系统", "打卡签到")


def prefers_non_system(ctx: dict) -> bool:
    """是否应按「非系统文 / 法器金手指」生成。"""
    logline = ctx.get("logline") or ""
    positioning = ctx.get("positioning") or {}
    taboos = " ".join(str(t) for t in (positioning.get("taboo_lines") or []))
    topic = (ctx.get("benchmark") or {}).get("topic") or ""
    blob = f"{logline}{taboos}{topic}"
    if any(m in blob for m in _SYSTEM_MARKERS):
        return False
    if any(m in blob for m in _ARTIFACT_MARKERS):
        return True
    gf = ctx.get("golden_finger") or {}
    gf_type = str(gf.get("type") or "")
    if gf_type and "系统" not in gf_type and "签到" not in gf_type:
        if any(k in gf_type for k in ("魔器", "法器", "魂幡", "魔经", "血炼", "血脉", "老爷爷")):
            return True
    return False


def benchmark_non_system_note(logline: str) -> str:
    """注入 benchmark 步 user prompt。"""
    if not any(m in logline for m in _ARTIFACT_MARKERS):
        return ""
    return (
        "\n【非系统文选题】创意已标明不要系统流：\n"
        "  - benchmark.topic 不得标为「系统流」，应标为「魔道修仙/法器流/黑暗生存」等；\n"
        "  - pitfalls_to_avoid 须含：系统面板、叮提示音、任务栏、属性弹窗、经验值界面；\n"
        "  - positioning.taboo_lines 须含至少 1 条「禁止系统 UI / 禁止叮」类硬禁忌。\n"
    )


def golden_finger_extra_block() -> str:
    return (
        "\n【非系统文 · 法器金手指硬约束】\n"
        "  - golden_finger.type 不得含「系统」「签到」「面板」；优先：血炼魔器/魔经残篇/魂幡/血脉/老爷爷；\n"
        "  - upgrade_mechanism 须叙事化（收魂代修、血祭认主、幡内亡魂反哺…），禁止任务/经验值/属性栏；\n"
        "  - restriction 须含实体代价（精血、认主、执法堂追责、幡损…）；\n"
        "  - 用 manifestation_style 描述能力呈现（器物异动、魔诀灌脑、体感暖流），"
        "★禁止 signature_lines 式「叮」提示音★。\n"
    )


def golden_finger_json_fields(*, artifact: bool) -> tuple[str, str]:
    """返回 (type_hint, extra_json_fields) 用于 golden_finger prompt。"""
    if artifact:
        type_hint = "类型（血炼魔器/魔经残篇/魂幡/血脉/老爷爷…★禁止系统/签到/面板★）"
        extra = (
            '    "manifestation_style": "能力如何呈现（血祭认主/魔诀灌脑/幡面异动/纯体感，禁止界面）",\n'
            '    "blood_price": "认主或发动的实体代价（精血/寿元/材料…）"\n'
        )
    else:
        type_hint = "类型（系统/吞噬/重生/天赋/老爷爷/签到…可组合）"
        extra = '    "signature_lines": ["1-2句标志性提示音/口头禅"]\n'
    return type_hint, extra


def chapter_outline_non_system_note() -> str:
    return (
        "\n【非系统文正文口径】本书金手指为法器/魔功，章纲与正文禁止："
        "叮、系统提示、面板弹出、任务完成、经验+100、属性栏。"
        "转折拍用血祭/认主/灌脑/器物异动，不用机械音。\n"
    )


def prose_system_taboo_block() -> str:
    return (
        "\n【非系统文硬约束】金手指是魔器/魔经，不是游戏系统："
        "禁止写「叮」、禁止属性面板/任务栏/经验值弹窗；"
        "升级与反馈只用叙事（暖流入体、幡内魂魄打坐、精血代价）。"
        "主角内心比喻（如「血汗工厂」）可偶尔一次，但不是 UI。\n"
    )
