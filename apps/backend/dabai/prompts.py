"""设定步骤 prompt 分发 + 兼容存根。

统一约定：
  - system 立「大白文总编辑」人设（prompt_base.SYS_BASE），强调爽点循环而非因果链。
  - user 末尾给出**精确 JSON 骨架**，并强制「只返回 JSON」。
  - 设定步深挖版（benchmark / golden_finger / factions / storylines / volumes）见
    prompts_setting；章纲两段式（节拍序列/五拍展开/定向修复）见 prompts_chapter；
    反派阶梯/谜题排程/书名简介的独立存根见 prompts_extra。
ctx 为累积上下文 dict（前序步骤产物）。

本文件只做分发 + 两个 derived 步（positioning / story_assets）的兼容存根；
设定主 prompt 已抽到 prompts_setting.py 以遵守 600 行红线。
"""

from __future__ import annotations

import json

from dabai import prompts_chapter, prompts_extra, prompts_plot_blueprint, prompts_setting
from dabai.config import DabaiConfig
from dabai.prompt_base import SYS_BASE, benchmark_block, ctx_brief

# 兼容旧引用名（外部可能 import）
_SYS_BASE = SYS_BASE
_ctx_brief = ctx_brief
_benchmark_block = benchmark_block


# ── derived 步兼容存根（pipeline 实际不单独调用，由 carrier 一次产出）─────────
def positioning(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """立项定位（derived：随 benchmark 合并步一次产出；保留以兼容潜在拆分调用）。"""
    user = (
        f"一句话创意：{ctx['logline']}\n"
        + benchmark_block(ctx) + "\n"
        "为这本大白文做立项定位。返回 JSON 对象：\n"
        "{\n"
        '  "target_audience": "目标读者画像（平台/年龄/口味）",\n'
        '  "shuang_pool": ["本书主打的爽点类型，从 打脸/升级/获宝/扮猪吃虎/装逼/群嘲反转/收小弟/救场/扬名 中选5-7个"],\n'
        '  "face_slap_frequency": "打脸/爽点频率（如每章一次小爽点，每5章一大爆点）",\n'
        '  "golden_three_strategy": "黄金三章情绪节拍（只写情绪/功能，禁止写具体场景）：'
        '第1章=憋屈蓄势+金手指端倪；第2章=疑→证（金手指见效）；第3章=首次当众爽点释放",\n'
        '  "pace_type": "fast",\n'
        '  "emotional_arc": "情绪闭环节律（憋屈→反击→扬名 的周期）",\n'
        '  "taboo_lines": ["3条硬禁忌，如 不许窝囊超过一章"],\n'
        '  "writing_style": "plain"\n'
        "}"
    )
    return SYS_BASE, user


def story_assets(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """剧情资产 + 初始关系（derived：随 storylines 合并步一次产出；保留兼容存根）。"""
    chars = ctx.get("characters") or []
    char_lines = "\n".join(
        f"  - {c.get('name', '')}（{c.get('role', '')}）：{(c.get('persona') or '')[:30]}"
        for c in chars[:8]
    )
    user = (
        f"{ctx_brief(ctx)}\n\n"
        f"【人物清单】\n{char_lines}\n\n"
        "设计两块台账种子，只返回 JSON：\n"
        "1. plot_assets：3-6 件有剧情功能的功法/道具（每件绑定剧情作用：\n"
        "   被各方觊觎的争夺点 / 反派底牌 / 主角功法升级路线 / 身世信物谜题）。\n"
        "2. initial_relations：主角与每个核心人物的开局关系（要有张力）。\n"
        "★debut 分流（硬约束）★：\n"
        "  - debut=start：仅「开局已持有」——他人持有的争夺点/底牌、主角随身身世信物等；\n"
        "  - debut=later：第1章及之后才获得的功法/宝物（含成长线主功法）；\n"
        "  - plot_role=成长线 的功法 ★必须★ debut=later。\n"
        "{\n"
        '  "plot_assets": [\n'
        '    {"kind": "skill|item", "name": "≤10字", "plot_role": "争夺点|底牌|成长线|身世信物",\n'
        '     "owner": "开局持有者人名（未登场则留空）", "debut": "start|later", "planned_volume": 1,\n'
        '     "description": "≤40字：谁觊觎/怎么升级/何时引爆"}\n'
        "  ],\n"
        '  "initial_relations": [\n'
        '    {"from": "主角人名", "to": "对方人名",\n'
        '     "attitude": "敌对|轻视|忌惮|臣服|效忠|盟友|暧昧|中立",\n'
        '     "tension": "≤30字初始张力（嫉妒/退婚之恨/暗中觊觎金手指）"}\n'
        "  ]\n"
        "}\n"
        "注意：金手指本身不要重复列入 plot_assets（已单独建账）。"
    )
    return SYS_BASE, user


# ── 分发 ─────────────────────────────────────────────────────────────────────
_BUILDERS = {
    "benchmark": prompts_setting.benchmark,          # ★合并：自动选材 + 定位
    "positioning": positioning,                      # derived 兼容存根
    "plot_blueprint": prompts_plot_blueprint.plot_blueprint,
    "golden_finger": prompts_setting.golden_finger,  # ★合并：金手指 + 境界 + 反派
    "antagonist_ladder": prompts_extra.antagonist_ladder,
    "factions": prompts_setting.factions,            # ★合并：势力 + 人物
    "storylines": prompts_setting.storylines,        # ★合并：故事线 + 资产 + 谜题
    "story_assets": story_assets,                    # derived 兼容存根
    "mystery_schedule": prompts_extra.mystery_schedule,
    "title_blurb": prompts_extra.title_blurb,
    "volumes": prompts_setting.volumes,
    "volume_chapters": prompts_chapter.volume_chapters,  # 单次整卷 beat+五拍（主路径）
    "beat_sequence": prompts_chapter.beat_sequence,      # 降级路径
    "chapter_outlines": prompts_chapter.chapter_outlines,  # 降级路径
    "chapter_repair": prompts_chapter.chapter_repair,
}


def build(step: str, ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """返回 (system, user)。未知步骤抛 KeyError。"""
    return _BUILDERS[step](ctx, cfg)


def dump_ctx_json(ctx: dict) -> str:  # 调试辅助
    return json.dumps(ctx, ensure_ascii=False, indent=2)
