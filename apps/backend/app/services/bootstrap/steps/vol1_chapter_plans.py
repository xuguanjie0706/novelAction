"""Bootstrap Step 12.5：第一卷章级大纲（chapter_plan）。"""

from __future__ import annotations

from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.parse import parse_json
from app.utils.chapter_numbering import normalize_chapter_plan_title


async def gen_vol1_chapter_plans(svc: Any, project: Project, volumes: list, ctx: dict) -> list:
    if not volumes:
        return []

    vol1 = next((v for v in volumes if v.sort_order == 0), volumes[0])
    planned = (vol1.extra or {}).get("planned_chapters", 30)
    if planned not in (30, 60):
        planned = 30

    system = "你是网络小说结构策划专家，擅长将宏观设定转化为可执行的章节级写作蓝图。只返回JSON数组。"

    char_lines = []
    for name in ctx.get("char_names", []):
        tier = "plot" if name not in ctx.get("core_char_names", []) else "core"
        realm = ctx.get("char_realms", {}).get(name, "")
        char_lines.append(f"{name}({tier},{realm})")
    char_snapshot = "、".join(char_lines)

    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    relation_triggers = ctx.get("relation_triggers", "（无）")
    villain_timelines = ctx.get("villain_timelines", [])
    villain_hint = "；".join(villain_timelines) if villain_timelines else "（无）"
    opening_contract = ctx.get("opening_contract") or (project.extra or {}).get("opening_contract", {})
    contract_hint = ""
    if opening_contract:
        contract_hint = (
            f"\n【已有开局承诺（章级大纲必须兑现）】\n"
            f"  第1章末钩子：{opening_contract.get('chapter1_hook','')}\n"
            f"  第3章爽点：{opening_contract.get('chapter3_payoff','')}\n"
            f"  第5章伏笔：{opening_contract.get('chapter5_foreshadow','')}\n"
            f"  第10章订阅钩：{opening_contract.get('chapter10_subscribe_reason','')}\n"
            f"  节奏规划：{opening_contract.get('chapter_rhythm','')}\n"
        )

    plot_npc_hint = ctx.get("plot_npc_summary", "")

    positioning = ctx.get("positioning") or {}
    tropes = "、".join(positioning.get("tropes", []))
    pace_type = positioning.get("pace_type", "medium")

    power_level_names = ctx.get("power_level_names", [])
    power_hint = ""
    if power_level_names:
        power_hint = f"\n境界体系层级：{' → '.join(power_level_names[:6])}（如有更多则省略）"

    words_per_chapter = 2200

    all_results: list[OutlineNode] = []

    batch_ranges = [(1, min(30, planned))]
    if planned > 30:
        batch_ranges.append((31, planned))

    for batch_start, batch_end in batch_ranges:
        batch_count = batch_end - batch_start + 1
        prev_summary = ""
        if all_results:
            prev_summary = "\n【前批末尾3章摘要（续写衔接用）】\n" + "\n".join(
                f"  第{n.sort_order + 1}章：{n.summary or ''}"
                for n in all_results[-3:]
            )

        prompt = f"""小说：《{ctx.get('project_title', '')}》  主角：{ctx.get('protagonist', '主角')}
创意：{ctx.get('logline', '')}
{vol1.title}（phase={vol1.phase}，共{planned}章）
卷摘要：{vol1.summary or ''}  核心冲突：{vol1.conflict or ''}

【人物阵容】{char_snapshot}
【开局配角功能】{plot_npc_hint or '（无）'}
【故事线】{storyline_summary}
【关系触发事件（可在对应章节引爆）】{relation_triggers}
【反派时间线】{villain_hint}
【核心爽点类型】{tropes or '（未设定）'}  节奏类型：{pace_type}{power_hint}{contract_hint}{prev_summary}

请为本卷第{batch_start}～{batch_end}章生成{batch_count}个章节计划，返回JSON数组：
[
  {{
    "chapter_number": {batch_start},
    "title": "第X章：章节标题（有画面感，≤12字）",
    "opening_hook": "开篇钩子：前500字核心手段，如何让读者第一句就无法放下（≤30字）",
    "core_event": "核心事件：本章存在的理由，具体到人物+行动+结果（≤60字）",
    "character_change": "人物变化：谁的认知/处境/关系发生了不可逆变化（≤30字）",
    "foreshadow": "伏笔管理：本章新埋的伏笔或回收的旧伏笔（格式：埋[xxx] 收[xxx]，无则填空字符串）",
    "end_hook": "章末钩子：读完最后一句停不下来的原因，具体到手法（≤30字，不能只写「留下悬念」）",
    "involved_characters": ["人物名1", "人物名2"],
    "storyline_refs": ["故事线名称（从已有故事线中选）"],
    "pacing": "fast/normal/slow/climax（章节节奏）",
    "emotional_tone": "exciting/tense/sad/romantic/mysterious/funny/epic/calm",
    "power_milestone": "若本章有境界突破/技能习得则描述，否则填空字符串",
    "has_face_slap": false,
    "has_emotional_beat": false,
    "expected_words": {words_per_chapter}
  }}
]
⚠️ 强制要求：
1. involved_characters 只能使用上方已知人物名，不要发明新名字
2. 每章 end_hook 必须具体（"主角沉思"/"悬念丛生"之类废话不合格）
3. 第1章和第3章的 opening_hook / end_hook 必须对应 chapter1_hook / chapter3_payoff 的要求（若有）
4. 若 planned=60，前30章节奏偏快（以爽点和信息密度驱动），后30章可有1-2章慢节奏铺垫
5. opening phase 每3章内至少有1次有感知的主角胜利或资源获取
6. storyline_refs 要交叉出现，不要只推进主线
7. foreshadow 字段：本卷内至少有2条贯穿始终的伏笔线，首次埋入章写"埋[xxx]"，回收章写"收[xxx]"
只返回JSON数组，不要解释。"""

        try:
            raw = await svc._call_with_retry(
                system, prompt, task="bootstrap.vol1_chapters", max_tokens=4096
            )
            batch_data = parse_json(raw)
            if not isinstance(batch_data, list):
                batch_data = batch_data.get("chapters", [])
        except Exception:
            continue

        char_name_to_id = ctx.get("char_name_to_id", {})
        storyline_ids_map = ctx.get("storyline_ids", {})

        for item in batch_data:
            ch_num = item.get("chapter_number", batch_start)
            involved_ids = [
                char_name_to_id[n]
                for n in item.get("involved_characters", [])
                if n in char_name_to_id
            ]
            sl_ids = [
                storyline_ids_map[n]
                for n in item.get("storyline_refs", [])
                if n in storyline_ids_map
            ]
            end_hook_val = (item.get("end_hook") or "").strip() or None
            node = OutlineNode(
                project_id=project.id,
                parent_id=vol1.id,
                node_type="chapter_plan",
                title=normalize_chapter_plan_title(ch_num, item.get("title")),
                summary=item.get("core_event") or item.get("summary"),
                conflict=item.get("character_change") or item.get("conflict"),
                hook=(item.get("opening_hook") or "").strip() or None,
                highlight=end_hook_val,
                phase=vol1.phase,
                pacing=item.get("pacing", "normal"),
                emotional_tone=item.get("emotional_tone"),
                power_milestone=item.get("power_milestone") or None,
                involved_character_ids=involved_ids,
                storyline_ids=sl_ids,
                expected_words=item.get("expected_words", words_per_chapter),
                sort_order=ch_num - 1,
                extra={
                    "foreshadow": (item.get("foreshadow") or "").strip(),
                    "end_hook": end_hook_val or "",
                    "has_face_slap": item.get("has_face_slap", False),
                    "has_emotional_beat": item.get("has_emotional_beat", False),
                    "bootstrap_generated": True,
                },
            )
            svc.db.add(node)
            all_results.append(node)

    if all_results:
        svc.db.commit()

    ctx["vol1_chapter_count"] = len(all_results)
    return all_results
