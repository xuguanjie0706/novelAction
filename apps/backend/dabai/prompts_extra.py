"""新增设定步骤 prompt：卷级反派阶梯 / 跨卷谜题排程 / 书名海选+简介。

三步动机（对照精品线缺口）：
  - antagonist_ladder：卷2+ 打脸对象不再凭空造名（对齐精品线 Step 4.5）；
  - mystery_schedule：长线追读靠谜题揭示节奏，不靠每章爽点硬撑；
  - title_blurb：番茄上架的书名+简介本身就是第一爽点（对齐精品线书名海选）。
"""

from __future__ import annotations

from dabai.config import DabaiConfig
from dabai.ctx_rich import assets_block, storylines_block
from dabai.naming import character_naming_prompt_block
from dabai.prompt_base import SYS_BASE, benchmark_block, ctx_brief, ladder_block


def antagonist_ladder(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """卷级反派阶梯：每卷一个主要对立面，压迫感与仇恨链逐卷升级。"""
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + ladder_block(ctx) + "\n"
        f"全书共 {cfg.volume_count} 卷。设计【卷级反派阶梯】——每卷一个主要对立面"
        "（Boss/压迫源），这是各卷打脸高潮的靶子，后续势力/人物步必须为其建档。"
        "返回 JSON 数组：\n"
        "[\n"
        "  {\n"
        '    "volume_number": 1,\n'
        '    "boss_name": "Boss 姓名",\n'
        '    "boss_faction": "所属势力（可新设，势力步必须建档）",\n'
        '    "boss_realm": "境界名", "boss_realm_rank": 2,\n'
        '    "motive": "为何与主角过不去（具体仇怨/利益冲突，禁止单纯看不顺眼）",\n'
        '    "pressure_style": "压迫方式（资源克扣/规则刁难/当众羞辱/追杀/夺宝…）",\n'
        '    "fate": "卷末下场（被当众打脸/重伤遁走/伏诛/臣服…）"\n'
        "  }\n"
        "]\n"
        "硬规则：\n"
        "1. boss_realm_rank 用境界档位数字，须略高于该卷主角预计档位（压迫感来源），"
        "且逐卷递增、不超体系最高档；\n"
        "2. 仇恨链升级：后卷 Boss 优先是前卷 Boss 的靠山/师门/家族（打倒一个引出更大的）；\n"
        "3. fate 不得连续两卷相同；禁止所有 Boss 出自同一势力；\n"
        "4. 第1卷 Boss 必须是开局就能接触到的近身压迫者（同门/管事/退婚家族级别），"
        "不要一上来就是隐世大佬。\n"
        + character_naming_prompt_block(ctx)
        + "\n5. boss_name 必须是 2~4 字具体姓名（禁止「卷1Boss」「执法堂甲」「弟子A」类占位）。"
    )
    return SYS_BASE, user


def mystery_schedule(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """跨卷谜题揭示排程：长线钩子的逐卷投放表。"""
    gf = ctx.get("golden_finger") or {}
    user = (
        f"{ctx_brief(ctx)}\n"
        + storylines_block(ctx)
        + assets_block(ctx) + "\n"
        "【谜题素材】\n"
        f"  - 金手指来历：{gf.get('name', '')}（{str(gf.get('core_ability') or '')[:50]}）\n"
        "  - 身世信物/争夺点：见上方剧情资产台账\n"
        "  - mystery 类故事线：见上方故事线\n\n"
        f"把长线谜题做成【跨卷揭示排程】（全书 {cfg.volume_count} 卷）。返回 JSON：\n"
        "{\n"
        '  "mysteries": [\n'
        "    {\n"
        '      "name": "谜题名（≤10字）",\n'
        '      "essence": "真相一句话（只给作者看，正文揭底前禁止说破）",\n'
        '      "hook_question": "读者侧悬念问题（如 系统为何选中他？）",\n'
        '      "reveals": [{"volume_number": 1, "reveal": "该卷透出的一小块具体信息"}],\n'
        '      "final_reveal_volume": 5\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "硬规则：\n"
        "1. 共 2-4 个谜题；每一卷至少有一个谜题动一动（reveals 覆盖全卷次）；\n"
        "2. reveals 信息逐次升级（碎片→指向→反转），禁止每卷重复同一句暗示；\n"
        "3. 最大谜题（金手指来历/身世）的 final_reveal_volume 放在全书后 1/3；\n"
        "4. 谜题之间要能互相咬合（身世信物指向金手指来历之类），不是孤立四条线。"
    )
    return SYS_BASE, user


def _volumes_digest(ctx: dict) -> str:
    """卷骨架摘要（title_blurb 后置到 volumes 之后，书名/简介可引用卷 Boss 与大爆点）。"""
    vols = ctx.get("volumes") or []
    if not vols:
        return ""
    lines = []
    for v in vols[:8]:
        if not isinstance(v, dict):
            continue
        boss = v.get("boss") or ""
        lines.append(
            f"  - {str(v.get('title') or '')[:20]}"
            + (f"｜Boss:{str(boss)[:12]}" if boss else "")
            + f"｜高潮:{str(v.get('volume_climax') or '')[:36]}"
        )
    if not lines:
        return ""
    return "【全书卷骨架（书名/简介可从中取最炸的钩子）】\n" + "\n".join(lines) + "\n"


def title_blurb(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """书名海选 + 上架简介：番茄点击的第一道爽点（后置于 volumes，独立保高温档）。"""
    user = (
        f"{ctx_brief(ctx)}\n"
        + benchmark_block(ctx)
        + _volumes_digest(ctx) + "\n"
        "为本书做【书名海选 + 上架简介】。\n"
        "书名 12-16 个候选，6 种策略轮换："
        "金手指直给（开局签到百年）/反差装逼（废柴的我吞了天骄）/境界宣言（我以凡躯镇万仙）/"
        "台词式（就凭你也配退婚？）/悬念式（谁在我脑子里收尸）/身份反转（杂役弟子竟是…）。"
        "每个按番茄移动端点击直觉打分（0-100）。\n"
        "简介 80-150 字：3-6 个短句，结构=憋屈处境+金手指登场+打脸承诺+一句钩子；"
        "口语直给，禁止文艺腔、禁止世界观说明。\n"
        "返回 JSON：\n"
        "{\n"
        '  "title_candidates": [\n'
        '    {"title": "≤12字", "strategy": "策略名", "score": 90, "reason": "≤20字"}\n'
        "  ],\n"
        '  "chosen_title": "得分最高且不与对标书撞名的一个",\n'
        '  "blurb": "上架简介"\n'
        "}\n"
        "硬规则：chosen_title 禁止与对标书名雷同（换皮可以，撞名不行）；"
        "候选里至少 2 个带数字或具体名词（人/宝/境界），禁止全是抽象四字。"
    )
    return SYS_BASE, user
