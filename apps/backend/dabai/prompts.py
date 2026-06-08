"""每步 JSON 导向 prompt（system + user 模板）。

统一约定：
  - system 立「大白文总编辑」人设，强调爽点循环而非因果链。
  - user 末尾给出**精确 JSON 骨架**，并强制「只返回 JSON」。
  - 章纲 prompt 是核心：要求先排爽点序列，再展开每章；显式禁止 choice_cost 思维。
ctx 为累积上下文 dict（前序步骤产物）。
"""

from __future__ import annotations

import json
from typing import Any

from dabai.config import DabaiConfig

_SYS_BASE = (
    "你是有15年经验的番茄/七猫大白文主编，专精移动端碎片化爽文。\n"
    "你的信条：读者要的是『情绪势能→爽点引爆→即时反馈→更强钩子』的循环，"
    "不是文学因果链。爽点要直给、要有观众、要让读者一眼看懂。\n"
    "信息密度要低，一次只讲一个新东西；金手指当章见效；主角不许窝囊超过一章。\n"
    "只返回 JSON，不要任何解释、注释或 markdown 说明文字。"
)


def _ctx_brief(ctx: dict) -> str:
    """把已生成产物压成紧凑上下文（喂给后续步骤）。"""
    parts = []
    if "logline" in ctx:
        parts.append(f"一句话创意：{ctx['logline']}")
    if "golden_finger" in ctx:
        gf = ctx["golden_finger"]
        parts.append(f"金手指：{gf.get('name')}（{gf.get('core_ability', '')[:40]}）")
    if "power_ladder" in ctx:
        lv = ctx["power_ladder"].get("levels", [])
        parts.append("境界：" + "→".join(x.get("name", "") for x in lv[:7]))
    if "characters" in ctx:
        names = "、".join(c.get("name", "") for c in ctx["characters"][:6])
        parts.append(f"人物：{names}")
    if "storylines" in ctx:
        sl = "、".join(s.get("name", "") for s in ctx["storylines"])
        parts.append(f"故事线：{sl}")
    return "\n".join(parts)


# ── 各步 user prompt 构造 ────────────────────────────────────────────────────
def positioning(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"一句话创意：{ctx['logline']}\n\n"
        "为这本大白文做立项定位。返回 JSON 对象：\n"
        "{\n"
        '  "target_audience": "目标读者画像（平台/年龄/口味）",\n'
        '  "shuang_pool": ["本书主打的爽点类型，从 打脸/升级/获宝/扮猪吃虎/装逼/群嘲反转/收小弟/救场/扬名 中选5-7个"],\n'
        '  "face_slap_frequency": "打脸/爽点频率（如每章一次小爽点，每5章一大爆点）",\n'
        '  "golden_three_strategy": "黄金三章策略：第1章怎么蓄憋屈，第2章金手指怎么登场，第3章怎么第一次大打脸",\n'
        '  "pace_type": "fast",\n'
        '  "emotional_arc": "情绪闭环节律（憋屈→反击→扬名 的周期）",\n'
        '  "taboo_lines": ["3条硬禁忌，如 不许窝囊超过一章"],\n'
        '  "writing_style": "plain"\n'
        "}"
    )
    return _SYS_BASE, user


def golden_finger(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计本书的金手指（大白文的爽点引擎，必须当章见效、能持续产出爽点）。返回 JSON：\n"
        "{\n"
        '  "name": "金手指名称",\n'
        '  "type": "类型（系统/吞噬/重生/天赋/老爷爷/签到…可组合）",\n'
        '  "core_ability": "核心能力（一句话说清主角靠它能干什么）",\n'
        '  "upgrade_mechanism": "怎么靠它变强（量化的升级路径，便于读者数着爽）",\n'
        '  "shuang_engine": "怎么持续产生爽点（越强的敌人/越稀有的宝越爽 在哪体现）",\n'
        '  "restriction": "限制（防止主角无敌到没张力，但不能是会劝退读者的长期代价）",\n'
        '  "signature_lines": ["1-2句标志性提示音/口头禅"]\n'
        "}"
    )
    return _SYS_BASE, user


def power_ladder(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计清晰可数的境界阶梯（升级爽的标尺，名字要好记、层级要分明）。返回 JSON：\n"
        "{\n"
        '  "name": "体系名称",\n'
        '  "levels": [\n'
        '    {"rank": 1, "name": "境界名", "desc": "一句话特征+突破条件"}\n'
        "  ]\n"
        "}\n"
        "要求 6-8 个大境界，rank 从 1 递增。"
    )
    return _SYS_BASE, user


def factions(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计 3-5 个势力。大白文势力的作用是『提供压迫主角的土壤』和『打脸对象的来源』。返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "name": "势力名",\n'
        '    "stance": "主角方/压迫方/中立资源/神秘势力",\n'
        '    "role": "在爽点循环里扮演什么（谁压迫主角、谁是打脸靶子土壤）",\n'
        '    "power_tier": "最高战力档",\n'
        '    "note": "前期/后期作用"\n'
        "  }\n"
        "]"
    )
    return _SYS_BASE, user


def characters(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计核心人物。大白文必须有：1个扮猪吃虎的主角、1个以上前期打脸对象、1个女主、若干工具人配角。返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "name": "姓名", "role": "主角/打脸对象/女主/导师/工具人配角",\n'
        '    "tier": "核心/配角",\n'
        '    "start_realm": "起始境界", "persona": "性格（一句话）",\n'
        '    "function": "在爽点循环里的功能（打脸靶子/救场/感情锚点/埋钩子）"\n'
        "  }\n"
        "]\n"
        "主角额外带 desire（最强欲望）、wound（憋屈来源）、golden_finger 字段。"
    )
    return _SYS_BASE, user


def storylines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        "设计 3-4 条故事线。主线必须是『升级打脸』，其余可含复仇线/感情线/身世谜题线。返回 JSON 数组：\n"
        '[{"name": "线名", "type": "main/revenge/romance/mystery", "summary": "一句话走向"}]'
    )
    return _SYS_BASE, user


def volumes(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        f"把全书拆成 {cfg.volume_count} 卷，每卷 {cfg.volume_chapters} 章。"
        "每卷给出爽点大节拍与卷末高潮。返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "volume_number": 1, "title": "第1卷 卷名",\n'
        '    "phase": "opening/rising/turning/dark_hour/climax",\n'
        f'    "planned_chapters": {cfg.volume_chapters},\n'
        '    "big_beats": ["本卷2-3个大爆点（打脸/越级/夺宝）"],\n'
        '    "volume_climax": "卷末高潮（最大的一次打脸或翻盘）",\n'
        '    "end_hook": "卷末钩子（勾下一卷）"\n'
        "  }\n"
        "]\n"
        "第1卷必须是新手村开局：退婚/被辱→觉醒金手指→当众打脸扬名。"
    )
    return _SYS_BASE, user


# ── 章纲：爽点节拍器（核心 prompt）──────────────────────────────────────────────
def chapter_outlines(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    vol = ctx.get("_target_volume", {})
    n = vol.get("planned_chapters", cfg.volume_chapters)
    pool = "、".join(cfg.shuang_pool)
    chars = "、".join(c.get("name", "") for c in ctx.get("characters", []))
    system = _SYS_BASE + (
        "\n\n【章纲专项 · 爽点节拍器】\n"
        "本任务的核心不是『欲望-障碍-选择-代价』那套精品文链路——"
        "★明确禁止给主角的爽点强加代价/后遗症★。大白文的章是：\n"
        "憋屈势能(yaqu_setup) → 爽点引爆(yinbao) → 爽感反馈(shuang_payoff，必须有观众) → 强钩子(end_hook)。\n"
        "先在脑中排好整卷的爽点类型序列（相邻章不重复、强度阶梯上升、黄金三章必有强爽点），再逐章展开。"
    )
    user = (
        f"{_ctx_brief(ctx)}\n\n"
        f"为《{vol.get('title', '第1卷')}》（phase={vol.get('phase')}）生成 {n} 章章纲。\n"
        f"本卷大爆点：{vol.get('big_beats')}\n本卷卷末高潮：{vol.get('volume_climax')}\n"
        f"可用人物：{chars}\n可用爽点类型：{pool}\n\n"
        "硬约束：\n"
        f"1. 黄金前 {cfg.golden_chapters} 章：第1章蓄憋屈+留金手指钩子，第2章金手指见效，第3章第一次当众大打脸。\n"
        "2. 相邻两章 shuang_type 不得相同；每 "
        f"{cfg.big_beat_every} 章至少一个 is_big_beat=true 的大爆点。\n"
        "3. shuang_payoff 必须写明『当着谁的面、爽在哪』，witnesses 至少 1 人（爽点必须有观众）。\n"
        f"4. 每章 new_info_count ≤ {cfg.max_new_info_per_chapter}（一次只引入一个新设定/新人物/新名词）。\n"
        "5. end_hook 必须具体（更强敌人登场/更大机缘/打脸预告），禁用『悬念丛生』『让人期待』套话。\n"
        "6. 禁止给主角爽点强加 choice_cost / 后遗症 / 道德负担。\n\n"
        f"返回 JSON 数组，{n} 个元素，每个：\n"
        "{\n"
        '  "chapter_number": 1, "title": "第X章 标题(≤10字)",\n'
        '  "shuang_type": "本章爽点类型(从可用类型选)",\n'
        '  "yaqu_setup": "憋屈势能：谁在压主角/什么不公",\n'
        '  "yinbao": "引爆：主角怎么靠金手指反转",\n'
        '  "shuang_payoff": "爽感量化：当着谁的面、爽在哪、对方什么反应",\n'
        '  "witnesses": ["见证者/被打脸者(≥1人)"],\n'
        '  "end_hook": "章末强钩子(具体)",\n'
        '  "new_info_count": 1,\n'
        '  "involved_characters": ["出场人物(用已知人物名)"],\n'
        '  "is_big_beat": false,\n'
        '  "expected_words": 2000\n'
        "}"
    )
    return system, user


# ── 分发 ─────────────────────────────────────────────────────────────────────
_BUILDERS = {
    "positioning": positioning,
    "golden_finger": golden_finger,
    "power_ladder": power_ladder,
    "factions": factions,
    "characters": characters,
    "storylines": storylines,
    "volumes": volumes,
    "chapter_outlines": chapter_outlines,
}


def build(step: str, ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """返回 (system, user)。未知步骤抛 KeyError。"""
    return _BUILDERS[step](ctx, cfg)


def dump_ctx_json(ctx: dict) -> str:  # 调试辅助
    return json.dumps(ctx, ensure_ascii=False, indent=2)
