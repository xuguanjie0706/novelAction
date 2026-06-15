"""第1章开局策略：按本书主题定制，禁止退婚+踹 cliff 等烂模板。

供 volumes / chapter_outlines prompt 与 linter 共用。
"""

from __future__ import annotations

import hashlib
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

# 开场形态菜单：与「底层差事被克扣」并列的入场原型，按书轮换打破千篇一律。
# 每本书据 logline 取不同起点，避免同题材所有书都用同一种开场。
_OPENING_MODES: tuple[str, ...] = (
    "任务/差事现场：主角正干一桩具体活计，半途被克扣/刁难/抢功",
    "交易纠纷：坊市/借贷/赌约/契约现场被压价、被坑、被赖账",
    "遇袭逃命：开篇就在被追杀/围堵/绝境里挣命，险中露出金手指端倪",
    "审讯质问：被执法/长辈/债主当场盘问、扣帽子、逼供，主角硬顶",
    "比试挑衅：被点名上场/被当众挑战，对方笃定主角必输",
    "偷听密谋：主角无意撞见针对自己或家族的算计，攥着秘密进退两难",
    "市井冲突：街头/酒肆/集市的小摩擦升级，牵出更大的压迫者",
    "血亲家族压迫：被本家/族亲/同宗当众贬损、夺产、逐出，金手指在屈辱里觉动",
)


def _book_seed(ctx: dict) -> int:
    """按 logline + 金手指名生成稳定种子：同书结果稳定，不同书拿到不同轮换起点。"""
    blob = str(ctx.get("logline") or "") + str(
        (ctx.get("golden_finger") or {}).get("name") or ""
    )
    if not blob:
        return 0
    return int(hashlib.md5(blob.encode("utf-8")).hexdigest(), 16)


def _rotated_modes(ctx: dict, n: int = 3) -> list[str]:
    """按书种子确定性轮换取 n 个不同开场形态（去重、稳定）。"""
    total = len(_OPENING_MODES)
    if total == 0:
        return []
    n = min(n, total)
    start = _book_seed(ctx) % total
    return [_OPENING_MODES[(start + i) % total] for i in range(n)]


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
    """从 logline/主角职能/金手指推导开局方向，并叠加按书轮换的差异化入场形态。"""
    blob = _theme_hint_blob(ctx)
    hits: list[str] = []
    for keys, hint in _THEME_OPENING_HINTS:
        if any(k in blob for k in keys):
            hits.append(hint)
    modes = "；".join(_rotated_modes(ctx, 3))
    if hits:
        tail = f"。可选入场形态（按本书任选其一并具体化，勿与同题材其它书撞）：{modes}" if modes else ""
        return "；".join(hits[:2]) + tail
    if modes:
        return (
            "本书无固定模板可套——从下列入场形态按主题任选其一并写具体："
            f"{modes}。再据主角此刻身份与 logline 落地：他在做什么、谁当面压他、"
            "不公如何落到动作与对话；禁止套用退婚/踹 cliff。"
        )
    return (
        "从主角日常身份与本书 logline 推导：他此刻在做什么、谁当面压他、"
        "不公如何具体落到动作与对话；禁止套用退婚/踹 cliff。"
    )


def first_chapter_opening_block(ctx: dict) -> str:
    """注入 volumes / chapter_outlines：第1章须主题定制开局。"""
    examples = theme_opening_examples(ctx)
    modes = _rotated_modes(ctx, 3)
    protag_fn = _protagonist_role(ctx) or "（见人物表主角 function）"
    gf = ctx.get("golden_finger") or {}
    mode_lines = "\n".join(f"     · {m}" for m in modes)
    mode_block = (
        f"  - 本书优先尝试的入场形态（任选其一并写具体，勿全书都用同一种）：\n{mode_lines}\n"
        if mode_lines else ""
    )
    return (
        "\n【第1章开局定制（硬约束，违反即废稿）】\n"
        "★禁止默认套用以下烂模板★：未婚妻/未婚夫退婚、演武场当众羞辱、"
        "一脚踹下悬崖/坠入乱葬岗、撕毁婚书、天才反派单纯嘲讽废物。\n"
        "★多样性铁律★：第1章不是统一的「宗门杂役被克扣」模板——必须先据本书"
        "主题/金手指/主角身份给出 2～3 个不同形态的开局候选，再择最贴合本书的一个落地；"
        "禁止与同题材其它书撞同一种开场、同一种压迫手法、同一处场景。\n"
        "第1章必须根据本书主题单独设计 opening：\n"
        f"  - 主角身份/职能：{protag_fn}\n"
        f"  - 金手指：{gf.get('name', '')}（{gf.get('core_ability', '')[:50]}）\n"
        f"  - 推荐方向（择其贴合者，禁止照抄）：{examples}\n"
        + mode_block
        + "  - yaqu_setup 须写清：主角正在做什么具体差事/处在什么具体困境、"
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
