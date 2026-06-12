"""第1章开局策略：按本书主题定制，禁止退婚+踹 cliff 等烂模板。

供 volumes / chapter_outlines prompt 与 linter 共用。
"""

from __future__ import annotations

import re
# 章纲字段命中即报 DB-13（仅第1章）
_BANNED_CH1_MARKERS = (
    "退婚", "悔婚", "退亲", "休书", "婚书已毁", "撕毁婚书", "当众毁约",
    "踹下", "踹入", "一脚踹", "踢下悬崖", "推下悬崖", "坠崖", "摔下悬崖",
    "未婚妻当众", "未婚妻退", "退婚书",
)

# 主题关键词 → 开局灵感（非强制，仅供模型对齐本书）
_THEME_OPENING_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("收尸", "埋尸", "阴尸", "乱葬", "炼尸", "尸堆"), (
        "收尸/埋尸日常劳作中被克扣灵石、甩脏活、同门抢功；"
        "或在乱葬岗作业时遭陷害/克扣防护，憋屈来自『低贱差事+弱肉强食』而非退婚。"
    )),
    (("魔门", "魔道", "邪修", "魂幡", "万魂幡", "血祭"), (
        "魔门底层差事/刑堂盘查/同门夺功；金手指在尸堆/禁地/血池边以血炼认主出现，"
        "禁止演武场退婚式开局。"
    )),
    (("宗门", "外门", "内门", "弟子"), (
        "任务分配不公、考核刁难、资源被克扣、被栽赃背锅；"
        "憋屈来自门规与权力，而非默认退婚。"
    )),
    (("坊市", "拍卖", "商会", "交易"), (
        "被压价、被抢货、被当肥羊；开局在交易/借贷/契约纠纷现场。"
    )),
    (("边境", "哨所", "矿脉", "灵田"), (
        "苦差/守夜/采掘中被克扣、遇险被推出去顶包。"
    )),
)


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


def theme_opening_examples(ctx: dict) -> str:
    """从 logline/主角职能/金手指推导 1～2 条开局方向（写入 prompt）。"""
    blob = _theme_hint_blob(ctx)
    hits: list[str] = []
    for keys, hint in _THEME_OPENING_HINTS:
        if any(k in blob for k in keys):
            hits.append(hint)
    if hits:
        return "；".join(hits[:2])
    return (
        "从主角日常身份与本书 logline 推导：他此刻在做什么、谁当面压他、"
        "不公如何具体落到动作与对话；禁止套用退婚/踹 cliff。"
    )


def first_chapter_opening_block(ctx: dict) -> str:
    """注入 volumes / chapter_outlines：第1章须主题定制开局。"""
    examples = theme_opening_examples(ctx)
    protag_fn = _protagonist_role(ctx) or "（见人物表主角 function）"
    gf = ctx.get("golden_finger") or {}
    return (
        "\n【第1章开局定制（硬约束，违反即废稿）】\n"
        "★禁止默认套用以下烂模板★：未婚妻/未婚夫退婚、演武场当众羞辱、"
        "一脚踹下悬崖/坠入乱葬岗、撕毁婚书、天才反派单纯嘲讽废物。\n"
        "第1章必须根据本书主题单独设计 opening：\n"
        f"  - 主角身份/职能：{protag_fn}\n"
        f"  - 金手指：{gf.get('name', '')}（{gf.get('core_ability', '')[:50]}）\n"
        f"  - 推荐方向（择其贴合者，禁止照抄）：{examples}\n"
        "  - yaqu_setup 须写清：主角正在做什么具体差事/处在什么具体困境、"
        "谁用什么方式压他（动作+台词），location 必须是该身份的日常场景而非泛化「演武场」；\n"
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
        "改 yaqu_setup/location：从主角日常差事与同门/执法压迫写起，"
        "参考 first_chapter_opening 模块，勿退婚+踹 cliff",
    )


def witness_stems(witness: str) -> tuple[str, ...]:
    """见证者匹配用：去括号备注 + 群体类通用词干（禁止硬编码具体书的人名）。"""
    base = re.sub(r"[（(][^）)]*[）)]", "", witness).strip()
    extra: tuple[str, ...] = ()
    if "狗腿子" in witness or "跟班" in witness:
        extra = ("狗腿子", "跟班", "护卫", "仆从")
    if "背影" in witness and base:
        extra = extra + (base,)
    return (base,) + extra if base else extra
