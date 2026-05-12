"""Bootstrap Step 9：卷级骨架。"""

from __future__ import annotations

import json
from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.outline_planning import words_to_plan


async def gen_volumes(svc: Any, project: Project, ctx: dict):
    """Bootstrap 阶段只生成卷级骨架（volume），不生成 chapter_plan。"""
    system = "你是网络小说结构策划专家。只返回JSON数组。"
    storyline_hint = (
        f"\n故事线（每卷 summary 应说明推进了哪条线）：{ctx.get('storyline_summary', '')}"
        if ctx.get('storyline_summary') else ""
    )
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    n_volumes = plan["total_volumes"]
    total_chapters_hint = plan["total_chapters"]

    positioning = ctx.get("positioning") or {}
    positioning_block = ""
    if isinstance(positioning, dict) and positioning:
        positioning_block = (
            "\n【立项定位（每卷必须贯彻）】\n"
            + json.dumps(positioning, ensure_ascii=False)
            + "\n"
        )
    kit_block = get_genre_kit_block(ctx)

    villain_timelines = ctx.get("villain_timelines", [])
    villain_block = ""
    if villain_timelines:
        villain_block = (
            "\n【反派行动时间线（卷级 phase 必须与之对齐）】\n"
            + "\n".join(f"- {vt}" for vt in villain_timelines)
            + "\n⚠️ 对齐规则：反派明显占优/主角处于劣势的卷 → phase=dark_hour；\n"
            "反派计划被终结/代价完全兑现的卷 → phase=climax。\n"
        )

    prompt = f"""小说：《{ctx['project_title']}》主角：{ctx.get('protagonist', '主角')}
创意：{ctx['logline']}
立意与类型：{ctx.get('premise', '')[:700] or '（未填写）'}
设定摘要：{ctx['settings_summary']}{storyline_hint}{villain_block}{positioning_block}{kit_block}

主线核心角色（固定卡司，非全书全部人物）：{', '.join(ctx.get('char_names', []))}
⚠️ 以上只是主线人物。每卷 summary/conflict 允许并鼓励提及未命名配角（如"某城守将""地下情报商""宗门长老"等职能角色），章节细化时会按需正式创建他们。

根据故事规模规划卷级结构，返回JSON数组。
【字数目标】全书目标：{tw:,}字，折合约{total_chapters_hint}章；**必须恰好 {n_volumes} 卷**（由目标字数推算，数组长度必须等于{n_volumes}；不得为多塞 phase 而加卷，卷少时合并阶段）。
每卷 planned_chapters 只能填 30 或 60（过渡/尾卷可填30），不要其他数字。
所有卷的 planned_chapters 之和须尽量接近{total_chapters_hint}章。

【phase 阶段标记（必填，单值）】每卷必须从下列阶段中选一个，全书必须按以下顺序大致单调推进：
  - opening    第一卷固定为开局期（新手村、立金手指、密集爽点）
  - rising     起飞期（势力扩张、感情线接入），通常 1-2 卷
  - turning    转折期（矛盾升级、代价兑现），通常 1 卷
  - dark_hour  至暗期（虐主、节奏放缓），通常 1 卷或与 turning 合并
  - climax     高潮期（伏笔回收、终战），通常 1 卷
  - ending     收束期（最终卷，留下一卷悬念种子）
若总卷数较少，可省略 dark_hour 或合并 turning + dark_hour，但 opening 与 climax 必须存在。

[
  {{
    "title": "第一卷：卷标题（有画面感，带悬念）",
    "sort_order": 0,
    "summary": "本卷核心剧情概述，60字内",
    "hook": "本卷核心悬念：读者最想知道的问题",
    "conflict": "本卷主要矛盾冲突",
    "planned_chapters": 60,
    "phase": "opening"
  }}
]
只返回JSON数组，不要任何说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.volumes",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("outline", data.get("volumes", []))

    valid_phases = {"opening", "rising", "turning", "dark_hour", "climax", "ending"}
    results = []
    for i, vol in enumerate(data):
        planned = vol.get("planned_chapters", 60)
        if planned not in (30, 60):
            planned = 60
        phase_val = (vol.get("phase") or "").strip().lower() or None
        if phase_val and phase_val not in valid_phases:
            phase_val = None
        if phase_val is None:
            total_hint = max(1, len(data))
            if i == 0:
                phase_val = "opening"
            elif i == total_hint - 1:
                phase_val = "ending"
            else:
                phase_val = "rising"
        node = OutlineNode(
            project_id=project.id,
            parent_id=None,
            node_type="volume",
            title=vol.get("title", f"第{i+1}卷"),
            summary=vol.get("summary"),
            hook=vol.get("hook"),
            conflict=vol.get("conflict"),
            sort_order=vol.get("sort_order", i),
            phase=phase_val,
            extra={"planned_chapters": planned, "phase": phase_val},
        )
        svc.db.add(node)
        results.append(node)

    svc.db.commit()
    ctx["volumes_summary"] = " | ".join(
        f"{n.title}：{(n.summary or '')[:40]}" for n in results
    )
    return results
