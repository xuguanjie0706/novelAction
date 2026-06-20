"""情节蓝图步 prompt：在 benchmark 已自动选材后，独立拆解高分对标书情节骨架。"""

from __future__ import annotations

import json

from dabai.config import DabaiConfig
from dabai.plot_blueprint import plot_blueprint_enabled
from dabai.prompt_base import SYS_BASE, ctx_brief


def plot_blueprint(ctx: dict, cfg: DabaiConfig) -> tuple[str, str]:
    """据 benchmark.reference_books + positioning，产出 plot_blueprints + adaptation_plan。"""
    bm = ctx.get("benchmark") or {}
    refs = bm.get("reference_books") or []
    pos = ctx.get("positioning") or {}
    ref_json = json.dumps(refs[:5], ensure_ascii=False, indent=2)
    shuang = "、".join(pos.get("shuang_pool") or [])[:80]

    system = (
        "你是精通番茄/起点爆款结构的情节解构主编，擅长把头部小说的「情节节拍」"
        "抽成可换皮改编的施工图。\n"
        "输入是已选定的高分对标书清单 + 本书 logline/定位；你的任务是：\n"
        "  ① 逐本拆解可借用的情节骨架（开篇弧/中段/高潮）；\n"
        "  ② 映射到本书各卷各章（adaptation_plan），供后续故事线/章纲直接施工。\n"
        "★合规★：只输出结构摘要与换皮策略，禁止抄录原文、禁止照搬人名地名原句。\n"
        "只返回 JSON。"
    )
    user = (
        f"{ctx_brief(ctx)}\n"
        f"目标读者：{pos.get('target_audience', '')}\n"
        f"主打爽点：{shuang}\n"
        f"黄金三章策略：{pos.get('golden_three_strategy', '')}\n\n"
        f"【已自动选定的高分对标书（须全部纳入拆解）】\n{ref_json}\n\n"
        f"把全书拆成 {cfg.volume_count} 卷、每卷 {cfg.volume_chapters} 章，"
        "返回 JSON：\n"
        "{\n"
        '  "plot_blueprints": [\n'
        '    {"title": "与 reference_books 对应的书名", "confidence": "high|medium|low",\n'
        '     "plot_role_in_adaptation": "本书借它什么（开篇母版/升级节奏/副线/高潮）",\n'
        '     "plot_skeleton": {\n'
        '       "opening_arc": [{"span": "约1-10章", "beats": "关键事件链（动词短语，≤80字）"}],\n'
        '       "mid_game": [{"span": "章段", "beats": "升级/换地图/新反派"}],\n'
        '       "climax_pattern": "卷末/全书高潮模式（一句话）"\n'
        "     },\n"
        '     "borrowable_beats": [\n'
        '       {"label": "节拍名(如退婚打脸/秘境夺宝)", "ref_span": "对标书章段",\n'
        '        "emotion_arc": "憋屈→扳机→爽", "adapt_hint": "换皮到本书 logline 时怎么改"}]\n'
        "    }\n"
        "  ],\n"
        '  "adaptation_plan": {\n'
        '    "strategy": "主借哪本开篇、哪本负责升级节奏（一句总策略）",\n'
        '    "volume_mapping": [{"volume": 1, "primary_ref": "书名",\n'
        f'      "ref_span": "对标书章段", "local_span": "本书第1卷1-{cfg.volume_chapters}章",\n'
        '      "adapted_arc": "换皮后本卷讲什么（3-5句）"}],\n'
        '    "chapter_beat_hints": [{"span": "1-5", "ref_beat": "借哪条 borrowable_beat",\n'
        '      "must_hit": "须兑现的功能（如法宝认主/首次代修爽点/首次反杀），禁止写具体桥段如克扣灵石/雨中羞辱"}],\n'
        '    "expansion_notes": ["相对对标要扩写/加戏 2-4 条"]\n'
        "  }\n"
        "}\n"
        "硬规则：plot_blueprints 须覆盖全部对标书；volume_mapping 须覆盖每一卷；"
        f"chapter_beat_hints 须覆盖第1卷 1-{cfg.volume_chapters} 章（分 5-8 个 span）；"
        "adapt_hint / adapted_arc 须贴合本书 logline 与金手指方向（尚未设计金手指时可按 logline 推断）。"
    )
    if not plot_blueprint_enabled(cfg=cfg, ctx=ctx):
        user = ctx_brief(ctx) + "\n（情节蓝图已关闭，返回空 plot_blueprints 与空 adaptation_plan 的 JSON。）"
    return system, user
