"""第1章开局策略：优先按 benchmark/情节蓝图对标改编，禁止退婚+踹 cliff 等烂模板。

供 volumes / chapter_outlines prompt 与 linter 共用。
"""

from __future__ import annotations

import re

from dabai.plot_blueprint import ch1_opening_guidance_block

# 章纲字段命中即报 DB-13（仅第1章）
_BANNED_CH1_MARKERS = (
    "退婚", "悔婚", "退亲", "休书", "婚书已毁", "撕毁婚书", "当众毁约",
    "踹下", "踹入", "一脚踹", "踢下悬崖", "推下悬崖", "坠崖", "摔下悬崖",
    "未婚妻当众", "未婚妻退", "退婚书",
)

# 第1章高频烂模板词组（DB-17 / DLB-06 共用；有 benchmark 开篇映射时跳过）
CH1_CLICHE_MARKERS: tuple[str, ...] = (
    "克扣", "养魂珠", "灵石", "管事", "踩", "手背", "冻疮",
    "拖着残躯", "雨中", "大雨", "暴雨", "克扣了三", "克扣了二",
)

# 无 benchmark 时的题材兜底（只给方向，不写死桥段）
_THEME_FALLBACK_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("收尸", "埋尸", "阴尸", "乱葬", "炼尸", "尸堆"), (
        "阴秽差事/禁地劳作类开局；压迫来自门规、同门或执法，须贴合 logline 具体化。"
    )),
    (("魔门", "魔道", "邪修", "魂幡", "万魂幡", "血祭"), (
        "魔门底层差事/刑堂/禁地；金手指在尸堆/血池边换皮出现，禁止演武场退婚式开局。"
    )),
    (("宗门", "外门", "内门", "弟子"), (
        "任务分配、考核、栽赃等门规权力压迫；禁止默认退婚模板。"
    )),
)


def _has_benchmark_opening(ctx: dict) -> bool:
    bm = ctx.get("benchmark") or {}
    if not isinstance(bm, dict):
        return False
    return bool(
        bm.get("reference_books")
        or bm.get("plot_blueprints")
        or (bm.get("adaptation_plan") or {}).get("chapter_beat_hints")
    )


OPENING_CLICHE_RULE_ID = "DLB-06"


def skip_ch1_cliche_lint(ctx: dict | None) -> bool:
    """有 benchmark 开篇映射时，cliché 词表让位于对标改编。"""
    return _has_benchmark_opening(ctx or {})


def _protagonist_role(ctx: dict) -> str:
    chars = ctx.get("characters") or []
    for c in chars:
        if not isinstance(c, dict):
            continue
        role = str(c.get("role") or "")
        if "主角" in role or role.lower() == "protagonist":
            return str(c.get("function") or c.get("persona") or role)
    return ""


def _theme_hint_blob(ctx: dict) -> str:
    parts = [
        str(ctx.get("logline") or ""),
        str((ctx.get("positioning") or {}).get("selling_point") or ""),
        str((ctx.get("positioning") or {}).get("tropes") or ""),
        _protagonist_role(ctx),
        str((ctx.get("golden_finger") or {}).get("name") or ""),
        str((ctx.get("golden_finger") or {}).get("type") or ""),
    ]
    return " ".join(parts)


def _theme_fallback_hint(ctx: dict) -> str:
    """无 benchmark 时按题材给兜底方向（不预设固定开场菜单）。"""
    blob = _theme_hint_blob(ctx)
    for keys, hint in _THEME_FALLBACK_HINTS:
        if any(k in blob for k in keys):
            return hint
    return (
        "从主角此刻身份与 logline 推导：他在做什么、谁当面压他、"
        "不公如何落到动作与对话；禁止套用退婚/踹 cliff。"
    )


def theme_opening_examples(ctx: dict) -> str:
    """第1章开局方向：有 benchmark 时只引用对标改编，否则题材兜底。"""
    if _has_benchmark_opening(ctx):
        block = ch1_opening_guidance_block(ctx)
        if block.strip():
            return block.strip()
    return _theme_fallback_hint(ctx)


def first_chapter_opening_block(ctx: dict) -> str:
    """注入 volumes / chapter_outlines：第1章须按对标书改编开局。"""
    benchmark_block = ch1_opening_guidance_block(ctx)
    protag_fn = _protagonist_role(ctx) or "（见人物表主角 function）"
    gf = ctx.get("golden_finger") or {}
    fallback = ""
    if not benchmark_block.strip():
        fallback = (
            f"  - 题材兜底（无 benchmark 时）：{_theme_fallback_hint(ctx)}\n"
            "  - 建书后须补全 benchmark/plot_blueprint，第1章开篇以对标改编为准。\n"
        )
    return (
        "\n【第1章开局定制（硬约束，违反即废稿）】\n"
        "★禁止默认套用以下烂模板★：未婚妻/未婚夫退婚、演武场当众羞辱、"
        "一脚踹下悬崖/坠入乱葬岗、撕毁婚书、天才反派单纯嘲讽废物。\n"
        "★开篇来源优先级★：① benchmark + 情节蓝图改编映射 → ② 卷 opening_setup → "
        "③ 本书 logline/主角身份；禁止用系统固定开场菜单替代对标书。\n"
        + (benchmark_block if benchmark_block.strip() else "")
        + fallback
        + "第1章 opening 须单独设计：\n"
        f"  - 主角身份/职能：{protag_fn}\n"
        f"  - 金手指：{gf.get('name', '')}（{gf.get('core_ability', '')[:50]}）\n"
        "  - yaqu_setup 须写清：主角正在做什么具体差事/处在什么具体困境、"
        "谁用什么方式压他（动作+台词），location 须贴合对标改编后的场景；\n"
        "  - 第1章 new_info_count 优先 ≤1，勿同时塞退婚+身世+第二宝物等多线；\n"
        "  - end_hook 指向金手指即将/刚刚露头，而非「悬念丛生」。\n"
    )


def ch1_outline_blob(ch: dict) -> str:
    """合并第1章章纲各字段用于 banned 检测。"""
    return " ".join(str(ch.get(k) or "") for k in (
        "title", "location", "yaqu_setup", "emotion_turn",
        "yinbao", "shuang_payoff", "end_hook",
    ))


def lint_banned_ch1_tropes(ch: dict) -> tuple[str, str] | None:
    """第1章命中烂模板则返回 (message, suggestion)。"""
    if int(ch.get("chapter_number") or 0) != 1:
        return None
    blob = ch1_outline_blob(ch)
    hits = [m for m in _BANNED_CH1_MARKERS if m in blob]
    if not hits:
        return None
    return (
        f"第1章套用烂模板：含「{'、'.join(hits[:3])}」——开局应贴合本书主题定制",
        "改 yaqu_setup/location：按 benchmark 改编映射换皮，勿退婚+踹 cliff",
    )


def lint_ch1_cliche_template(
    ch: dict, ctx: dict | None = None,
) -> tuple[str, str] | None:
    """DB-17：第1章命中系统内高频坍缩模板（无 benchmark 映射时）。"""
    if skip_ch1_cliche_lint(ctx):
        return None
    if int(ch.get("chapter_number") or 0) != 1:
        return None
    blob = ch1_outline_blob(ch)
    hits = [m for m in CH1_CLICHE_MARKERS if m in blob]
    if len(hits) < 2:
        return None
    strong = {"克扣", "管事", "雨中", "大雨", "踩", "手背", "拖着残躯", "养魂珠"}
    if len(hits) >= 3 or len(strong.intersection(hits)) >= 2:
        return (
            f"第1章疑似套用系统默认收尸模板（非对标改编）：命中「{'、'.join(hits[:4])}」",
            "按 benchmark.adaptation_plan 第1章节拍 + 卷 opening_setup 换皮重写 yaqu；"
            "若对标书确有类似压迫，须写出改编差异（人物/场景/动作），禁止与同题材它书雷同",
        )
    return None


def prose_opening_cliche_hit(
    opening_text: str, *, ctx: dict | None = None,
) -> tuple[str, str] | None:
    """DLB-06：正文开篇 450 字命中系统默认 ch1 模板组合。"""
    if skip_ch1_cliche_lint(ctx):
        return None
    head = (opening_text or "")[:450]
    if not head.strip():
        return None
    hits = [m for m in CH1_CLICHE_MARKERS if m in head]
    strong = {"克扣", "管事", "雨中", "大雨", "暴雨", "踩", "手背", "拖着残躯"}
    rain = any(x in head for x in ("雨中", "大雨", "暴雨", "雨水", "雨幕"))
    if rain and len(hits) >= 2 and len(strong.intersection(hits)) >= 2:
        return (
            f"开篇疑似套用系统默认模板（雨中+{'、'.join(h for h in hits[:3] if h in strong)}）",
            "按导演单与对标改编换皮开笔；若对标书确有类似开场，须写出本书专属人物/场景/动作",
        )
    if len(hits) >= 3 and len(strong.intersection(hits)) >= 2:
        return (
            f"开篇命中系统默认模板词：{'、'.join(hits[:4])}",
            "按 benchmark 改编映射与 beat_execution 换写法，勿照抄章纲或它书套话",
        )
    return None


def witness_stems(witness: str) -> tuple[str, ...]:
    """见证者匹配用：去括号备注 + 群体类通用词干（禁止硬编码具体书的人名）。"""
    base = re.sub(r"[（(][^）)]*[）)]", "", witness).strip()
    extra: tuple[str, ...] = ()
    if "狗腿子" in witness or "跟班" in witness:
        extra = ("狗腿子", "跟班", "护卫", "仆从")
    if "背影" in witness and base:
        extra = extra + (base,)
    return (base,) + extra if base else extra
