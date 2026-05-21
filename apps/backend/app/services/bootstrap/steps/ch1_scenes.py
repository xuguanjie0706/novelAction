"""Bootstrap Step 13：第1章场景蓝图。"""

from __future__ import annotations

from typing import Any

from app.models import Project, Scene
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion


async def gen_ch1_scenes(svc: Any, project: Project, vol1_plans: list, ctx: dict) -> list:
    if not vol1_plans:
        return []

    ch1_node = vol1_plans[0]

    system = "你是网络小说分场设计专家。只返回JSON数组。"

    ch1_summary = ch1_node.summary or ""
    ch1_conflict = ch1_node.conflict or ""
    ch1_hook = ch1_node.hook or ""

    opening_contract = ctx.get("opening_contract") or {}
    first_200 = opening_contract.get("first_200_words_test", "")
    ch1_hook_req = opening_contract.get("chapter1_hook", "")

    protagonist = ctx.get("protagonist", "主角")
    world_hint = ctx.get("world_overview", "")[:200]
    power_hint = ctx.get("power_summary", "")[:100]
    positioning = ctx.get("positioning") or {}
    pace_type = positioning.get("pace_type", "medium")

    # 根据节奏类型动态调整场景字数：快节奏场景短而密，慢节奏场景深而长
    words_per_scene = {"fast": 450, "slow": 650}.get(pace_type, 550)

    prompt = f"""小说：《{ctx.get('project_title', '')}》  主角：{protagonist}
创意：{ctx.get('logline', '')}
世界背景（供选择地点）：{world_hint}
境界提示：{power_hint}

【第1章节点信息】
摘要：{ch1_summary}
核心冲突：{ch1_conflict}
章末钩子：{ch1_hook}

【开局承诺对第1章的要求】
前200字必须完成：{first_200 or '（未设定）'}
章末必须埋下的钩子：{ch1_hook_req or '（未设定）'}
节奏类型：{pace_type}

请为第1章设计 3-5 个分场（Scene），返回JSON数组：
[
  {{
    "order": 1,
    "title": "场标题（可选，≤10字）",
    "time": "故事内时间（如：第1日·晨）",
    "location_name": "具体地点（结合世界背景，≤15字）",
    "pov_character": "视点人物名（通常是主角）",
    "characters_on_stage": ["在场人物名1", "在场人物名2"],
    "goal": "本场角色想达成的目标（≤20字）",
    "conflict": "阻碍目标实现的障碍或对立（≤20字）",
    "turn": "本场发生的关键转变（≤20字）",
    "hook": "场末留下的疑问或紧张（≤15字，最后一场写章末大钩）",
    "hook_strength": 4,
    "word_budget": {words_per_scene},
    "pacing": "fast/mid/slow",
    "sensory_focus": "sight/sound/smell/taste/touch/mixed"
  }}
]
⚠️ 要求：
1. 第1场必须在前100字内建立主角处境的压力或不公（不要废话开场）
2. 至少有1场包含主角的主动行动（不能全是被动被安排）
3. 最后一场的 hook 必须对应上方「章末必须埋下的钩子」要求
4. pov_character 和 characters_on_stage 中只能用上方已知的人物名
5. 各场字数预算之和约为 {words_per_scene * 4}-{words_per_scene * 5} 字（{pace_type} 节奏标准）
只返回JSON数组，不要解释。"""

    try:
        raw = await svc._call_with_retry(
            system,
            prompt,
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.ch1_scenes",
        )
        data = parse_json(raw)
        if not isinstance(data, list):
            data = data.get("scenes", [])
    except Exception:
        return []

    char_name_to_id = ctx.get("char_name_to_id", {})
    results: list = []

    for item in data:
        pov_name = item.get("pov_character", protagonist)
        pov_id = char_name_to_id.get(pov_name)

        on_stage_ids = [
            char_name_to_id[n]
            for n in item.get("characters_on_stage", [])
            if n in char_name_to_id
        ]

        scene = Scene(
            project_id=project.id,
            chapter_id=None,
            outline_node_id=ch1_node.id,
            order=item.get("order", len(results) + 1),
            title=item.get("title") or None,
            time=item.get("time") or None,
            location_name=item.get("location_name") or None,
            pov_character_id=pov_id,
            characters_on_stage=on_stage_ids,
            goal=item.get("goal"),
            conflict=item.get("conflict"),
            turn=item.get("turn"),
            hook=item.get("hook"),
            hook_strength=int(item.get("hook_strength", 3)),
            word_budget=int(item.get("word_budget", words_per_scene)),
            pacing=item.get("pacing", "mid"),
            sensory_focus=item.get("sensory_focus", "mixed"),
            status="planned",
            content=None,
            extra={"bootstrap_generated": True},
        )
        svc.db.add(scene)
        results.append(scene)

    if results:
        svc.db.commit()

    return results
