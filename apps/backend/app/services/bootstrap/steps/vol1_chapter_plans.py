"""Bootstrap Step 12.5：第一卷章级大纲（chapter_plan）。

设计原则
--------
章节计划不是"事件清单"，而是"主角欲望→障碍→选择→代价"的因果链。
每章必须回答：主角主动想要什么？什么挡住了他？他做了什么选择（揭示性格）？
这个选择的代价如何喂给下一章？只有这样，章节之间才有真正的叙事张力。
"""

from __future__ import annotations

from typing import Any

import logging

from app.models import OutlineNode, Project
from app.services.bootstrap.context_vol_expand import _build_reader_promises_block
from app.services.bootstrap.foreshadow_sync import sync_chapter_foreshadow
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.chapter_plan_batches import (
    chapter_plan_batch_ranges,
    log_chapter_plan_batches,
    normalize_volume_planned_chapters,
)
from app.services.bootstrap.steps.phase_guidance import (
    chapter_number_for_batch_item,
    get_chapter_phase_guidance,
    wipe_volume_chapter_plans,
)
from app.services.llm_token_budgets import max_tokens_vol1_chapter_plans
from app.services.outline_planning import (
    build_book_budget_block,
    chapter_word_budget_for_phase,
    words_to_plan,
)
from app.utils.chapter_numbering import normalize_chapter_plan_title

logger = logging.getLogger(__name__)

# 节奏约束函数从共享模块引入，不在此重复定义
# 如需自定义 vol1 行为，在 phase_guidance.py 增加参数而非复制函数
_get_chapter_phase_guidance = get_chapter_phase_guidance


async def gen_vol1_chapter_plans(svc: Any, project: Project, volumes: list, ctx: dict) -> list:
    """生成第一卷章级大纲节点（chapter_plan）。

    Args:
        svc: Bootstrap 服务实例（提供 _call_with_retry / db）。
        project: 当前项目模型。
        volumes: bootstrap Step9 生成的卷节点列表。
        ctx: 全局 bootstrap 上下文字典。

    Returns:
        已落库的 OutlineNode 列表（chapter_plan 类型）。
    """
    if not volumes:
        logger.warning("vol1_chapters 跳过：无卷节点 project=%s", project.id)
        return []

    vol1 = next((v for v in volumes if v.sort_order == 0), volumes[0])
    planned = normalize_volume_planned_chapters((vol1.extra or {}).get("planned_chapters", 30))

    logger.info(
        "vol1_chapters 开始 project=%s volume=%s planned=%d phase=%s",
        project.id,
        vol1.id,
        planned,
        vol1.phase or "opening",
    )

    # 重试 / 重复执行时先清旧章纲，避免同 sort_order 叠多条（graph retry 不调 wipe_step）
    wiped = wipe_volume_chapter_plans(svc.db, project.id, vol1.id)
    if wiped:
        logger.info(
            "vol1_chapters 已清除旧章纲 project=%s volume=%s count=%d",
            project.id,
            vol1.id,
            wiped,
        )

    system = (
        "你是拥有30年经验的网络小说结构策划。"
        "你深知：章节的核心不是「发生了什么」，而是「主角主动想要什么→什么挡住了他→"
        "他做了什么选择（这个选择暴露性格）→选择的代价喂给了下一章」。"
        "只返回JSON数组，不要任何说明文字。"
    )

    # ── 人物快照 ──────────────────────────────────────────────────
    char_lines = []
    for name in ctx.get("char_names", []):
        tier = "plot" if name not in ctx.get("core_char_names", []) else "core"
        realm = ctx.get("char_realms", {}).get(name, "")
        char_lines.append(f"{name}({tier},{realm})")
    char_snapshot = "、".join(char_lines)

    # ── 主角心理档案（来自 Character 生成时写入 ctx）────────────────
    protagonist = ctx.get("protagonist", "主角")
    protag_psychology = ""
    char_profiles = ctx.get("char_profiles", {})  # {name: {core_wound, current_desire, biggest_lie}}
    if protagonist in char_profiles:
        p = char_profiles[protagonist]
        protag_psychology = (
            f"\n【主角心理档案（章节行为的底层驱动，高优先级约束）】\n"
            f"  核心创伤/恐惧：{p.get('core_wound', '（未设定）')}\n"
            f"  当前最强烈欲望：{p.get('current_desire', '（未设定）')}\n"
            f"  当前最大谎言（将被打破的错误信念）：{p.get('biggest_lie', '（未设定）')}\n"
            f"  主要关系压力：{p.get('relationship_pressure', '（未设定）')}\n"
        )

    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    relation_triggers = ctx.get("relation_triggers", "（无）")
    villain_timelines = ctx.get("villain_timelines", [])
    villain_hint = "；".join(villain_timelines) if villain_timelines else "（无）"

    opening_contract = ctx.get("opening_contract") or (project.extra or {}).get("opening_contract", {})
    contract_hint = ""
    if opening_contract:
        contract_hint = (
            f"\n【已有开局承诺（章级大纲必须兑现）】\n"
            f"  第1章末钩子：{opening_contract.get('chapter1_hook', '')}\n"
            f"  第3章爽点：{opening_contract.get('chapter3_payoff', '')}\n"
            f"  第5章伏笔：{opening_contract.get('chapter5_foreshadow', '')}\n"
            f"  第10章订阅钩：{opening_contract.get('chapter10_subscribe_reason', '')}\n"
            f"  节奏规划：{opening_contract.get('chapter_rhythm', '')}\n"
        )

    reader_promises_block = _build_reader_promises_block(svc.db, str(project.id))

    plot_npc_hint = ctx.get("plot_npc_summary", "")
    positioning = ctx.get("positioning") or {}
    tropes = "、".join(positioning.get("tropes", []))
    pace_type = positioning.get("pace_type", "medium")

    power_level_names = ctx.get("power_level_names", [])
    power_hint = ""
    if power_level_names:
        power_hint = f"\n境界体系层级：{' → '.join(power_level_names[:6])}（如有更多则省略）"

    # ── 全书预算锚点（从 ctx 读取，ctx 由 gen_volumes 初始化；兜底用 target_words 重算）──
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    quota_total = ctx.get("chapter_quota_total", plan["total_chapters"])
    quota_total_volumes = ctx.get("chapter_quota_total_volumes", plan["total_volumes"])
    quota_used = ctx.get("chapter_quota_used", 0)

    all_results: list[OutlineNode] = []

    completion_budget = max_tokens_vol1_chapter_plans()
    batch_ranges = chapter_plan_batch_ranges(planned, completion_budget)
    log_chapter_plan_batches(
        logger,
        tag="vol1_chapters",
        planned=planned,
        ranges=batch_ranges,
        max_completion_tokens=completion_budget,
    )

    for batch_start, batch_end in batch_ranges:
        batch_count = batch_end - batch_start + 1

        # 批次延续锚：用前批最后3章的"选择代价"驱动下一批开头
        prev_summary = ""
        if all_results:
            anchor_lines = []
            for n in all_results[-3:]:
                ex = n.extra or {}
                cost = ex.get("choice_cost", "")
                anchor_lines.append(
                    f"  第{n.sort_order + 1}章：{n.summary or ''}（遗留代价：{cost}）"
                )
            prev_summary = "\n【前批末尾3章遗留代价（本批第一章必须承接）】\n" + "\n".join(anchor_lines)

        # 按章节区间注入细分节奏约束
        phase_guidance_lines = []
        for ch in range(batch_start, batch_end + 1):
            g = _get_chapter_phase_guidance(ch, planned, vol1.phase or "opening")
            if g and g not in phase_guidance_lines:
                phase_guidance_lines.append(g)
        phase_block = ""
        if phase_guidance_lines:
            phase_block = "\n【本批节奏约束（按章节区间）】\n" + "\n".join(
                f"  - {g}" for g in phase_guidance_lines
            )

        # 全书预算约束块（防漂移核心）
        budget_block = build_book_budget_block(
            target_words=tw,
            total_chapters=quota_total,
            total_volumes=quota_total_volumes,
            volume_quota=planned,
            chapters_used_so_far=quota_used,
            batch_start=batch_start,
            batch_end=batch_end,
        )

        prompt = f"""小说：《{ctx.get('project_title', '')}》  主角：{protagonist}
创意：{ctx.get('logline', '')}
{vol1.title}（phase={vol1.phase}，共{planned}章）
卷摘要：{vol1.summary or ''}  核心冲突：{vol1.conflict or ''}

【人物阵容】{char_snapshot}
【开局配角功能】{plot_npc_hint or '（无）'}
【故事线】{storyline_summary}
【关系触发事件（可在对应章节引爆）】{relation_triggers}
【反派时间线】{villain_hint}
【核心爽点类型】{tropes or '（未设定）'}  节奏类型：{pace_type}{power_hint}{protag_psychology}{contract_hint}{reader_promises_block}{phase_block}{prev_summary}{budget_block}

请为本卷第{batch_start}～{batch_end}章生成{batch_count}个章节计划，返回JSON数组：
[
  {{
    "chapter_number": {batch_start},
    "title": "第X章：章节标题（有画面感，≤12字）",
    "protagonist_want": "主角这一章主动想要什么（必须是主动欲望，不是「被逼应付」）",
    "protagonist_obstacle": "什么具体阻止了他（内部恐惧或外部冲突，不能只写「敌人」）",
    "protagonist_choice": "他做了什么关键选择（这个选择必须暴露性格，而不只是解决问题）",
    "choice_cost": "这个选择的代价（喂给下一章的债务，不能零代价）",
    "opening_hook": "开篇钩子：前500字核心手段，如何让读者第一句无法放下（≤30字）",
    "core_event": "核心事件：必须是主角选择的直接后果，格式「因[choice]→[result]」（≤60字）",
    "character_change": "人物变化：谁的认知/处境/关系发生了不可逆变化（≤30字）",
    "foreshadow": "伏笔管理：埋[伏笔内容|主题:与全书立意的关联] 收[伏笔内容] 加热[伏笔代号+推进方式]（无则填空）",
    "promise_fulfilled": "本章兑现了哪条读者承诺（填承诺原文关键词片段，无则填空字符串）",
    "villain_action": "反派这一章在做什么（即便不是本章视角），以及如何逼迫主角",
    "end_hook": "章末钩子：读完最后一句停不下来的原因，具体到手法（≤30字，禁用「留下悬念」）",
    "reader_emotion_target": "本章结束时读者的目标情绪（exciting/tense/sad/romantic/mysterious/warm/anxious/epic）",
    "involved_characters": ["人物名1", "人物名2"],
    "storyline_refs": ["故事线名称（从已有故事线中选）"],
    "pacing": "fast/normal/slow/climax",
    "emotional_tone": "exciting/tense/sad/romantic/mysterious/funny/epic/calm",
    "power_milestone": "若本章有境界突破/技能习得则描述，否则填空字符串",
    "has_face_slap": false,
    "has_emotional_beat": false,
    "expected_words": 2200
  }}
]
（expected_words 参考：opening/ending≈2000-2400，rising≈2300，turning≈2400，dark_hour≈2600-2800，climax≈3000-3300；fast 节奏-200，slow/climax 节奏+200-500；有打脸/情感高点+200。请按章节实际情况填写，不要全部填同一个数字。）
⚠️ 强制要求：
1. involved_characters 只能使用上方已知人物名，不要发明新名字
2. core_event 必须是 protagonist_choice 的直接后果，不能与 choice 无关
3. choice_cost 不能为空——零代价的选择不是戏剧，必须为下一章留下债务
4. villain_action 不能只写"（无）"——反派在大格局中始终有独立行动
5. end_hook 必须具体（"主角沉思"/"悬念丛生"之类废话不合格）
6. 第1章和第3章的 opening_hook/end_hook 必须对应 chapter1_hook/chapter3_payoff 的要求（若有）
7. opening phase 每3章内至少有1次主角主动发起的胜利或资源获取
8. storyline_refs 要交叉出现，不要只推进主线
9. foreshadow 字段：本卷内至少2条贯穿始终的伏笔线，埋入章写「埋[xxx|主题:yyy]」，回收章写「收[xxx]」
10. 🔴🟠级读者承诺必须在承诺窗口内的某一章填写 promise_fulfilled（与承诺原文有关键词重叠），不得拖欠
只返回JSON数组，不要解释。"""

        batch_data: list = []
        raw = ""
        for gen_attempt in range(2):
            try:
                raw = await svc._call_with_retry(
                    system,
                    prompt,
                    task="bootstrap.vol1_chapters",
                    max_tokens=completion_budget,
                )
                batch_data = parse_json(raw)
                if not isinstance(batch_data, list):
                    batch_data = batch_data.get("chapters", [])
            except Exception as exc:
                logger.warning(
                    "vol1_chapters JSON 解析/调用失败 project=%s batch=%d-%d "
                    "attempt=%d: %s; raw_tail=%r",
                    project.id,
                    batch_start,
                    batch_end,
                    gen_attempt + 1,
                    exc,
                    (raw or "")[-500:],
                )
                batch_data = []
                break

            actual_count = len(batch_data)
            if actual_count == batch_count:
                break
            if gen_attempt == 0:
                logger.warning(
                    "GEN-01 批次数漂移，重试：期望%d章，实际%d章（project=%s 批次=%d-%d）",
                    batch_count,
                    actual_count,
                    project.id,
                    batch_start,
                    batch_end,
                )
                continue
            logger.warning(
                "GEN-01 批次数仍不符，截断：期望%d 实际%d（project=%s 批次=%d-%d）",
                batch_count,
                actual_count,
                project.id,
                batch_start,
                batch_end,
            )
            batch_data = batch_data[:batch_count]

        if not batch_data:
            logger.warning(
                "vol1_chapters 批次无有效章纲，已跳过 project=%s batch=%d-%d "
                "planned=%d accumulated=%d",
                project.id,
                batch_start,
                batch_end,
                planned,
                len(all_results),
            )
            continue

        char_name_to_id = ctx.get("char_name_to_id", {})
        storyline_ids_map = ctx.get("storyline_ids", {})

        for batch_index, item in enumerate(batch_data):
            ch_num = chapter_number_for_batch_item(batch_start, batch_index, item)
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
            pacing_val = item.get("pacing", "normal")
            has_slap = bool(item.get("has_face_slap", False))
            has_beat = bool(item.get("has_emotional_beat", False))
            # AI 给出的 expected_words 优先，但用动态预算函数做兜底（防止 AI 全写同一数字）
            ai_words = item.get("expected_words")
            dynamic_words = chapter_word_budget_for_phase(
                vol1.phase or "opening", pacing_val, has_slap, has_beat
            )
            expected_words_val = ai_words if isinstance(ai_words, int) and 1500 <= ai_words <= 4000 else dynamic_words
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
                pacing=pacing_val,
                emotional_tone=item.get("emotional_tone"),
                power_milestone=item.get("power_milestone") or None,
                involved_character_ids=involved_ids,
                storyline_ids=sl_ids,
                expected_words=expected_words_val,
                sort_order=ch_num - 1,
                extra={
                    "foreshadow": (item.get("foreshadow") or "").strip(),
                    "promise_fulfilled": (item.get("promise_fulfilled") or "").strip(),
                    "end_hook": end_hook_val or "",
                    "has_face_slap": item.get("has_face_slap", False),
                    "has_emotional_beat": item.get("has_emotional_beat", False),
                    # ── 新增：主角欲望-障碍-选择-代价四元组 ──────────
                    "protagonist_want": (item.get("protagonist_want") or "").strip(),
                    "protagonist_obstacle": (item.get("protagonist_obstacle") or "").strip(),
                    "protagonist_choice": (item.get("protagonist_choice") or "").strip(),
                    "choice_cost": (item.get("choice_cost") or "").strip(),
                    # ── 新增：反派行动对齐 ────────────────────────────
                    "villain_action": (item.get("villain_action") or "").strip(),
                    # ── 新增：读者情绪目标 ────────────────────────────
                    "reader_emotion_target": (item.get("reader_emotion_target") or "").strip(),
                    "bootstrap_generated": True,
                },
            )
            svc.db.add(node)
            svc.db.flush()  # 让 node.id 可用，伏笔同步需要引用它
            sync_chapter_foreshadow(svc.db, project.id, node, ch_num)
            all_results.append(node)

    if all_results:
        from app.services.outline_linter.gate import finalize_volume_chapter_commit

        finalize_volume_chapter_commit(
            svc, project, vol1, all_results, ctx=ctx,
        )
        if ctx.get("linter_blocked"):
            block_payload = ctx.get("linter_block_payload") or {}
            logger.error(
                "GEN-02 第一卷章纲被 linter 阻断 project=%s volume=%s "
                "chapters=%d rules=%s",
                project.id,
                vol1.id,
                len(all_results),
                block_payload.get("linter_blocking_rules"),
            )

    if len(all_results) < planned:
        logger.warning(
            "vol1_chapters 章纲不完整 project=%s 期望=%d 实际=%d linter_blocked=%s",
            project.id,
            planned,
            len(all_results),
            bool(ctx.get("linter_blocked")),
        )
    elif not all_results:
        logger.error(
            "vol1_chapters 未生成任何章纲 project=%s planned=%d",
            project.id,
            planned,
        )
    else:
        logger.info(
            "vol1_chapters 完成 project=%s chapters=%d linter_blocked=%s",
            project.id,
            len(all_results),
            bool(ctx.get("linter_blocked")),
        )

    ctx["vol1_chapter_count"] = len(all_results)
    # 全书配额计数器累加（供后续卷展开时读取，防止漂移）
    ctx["chapter_quota_used"] = quota_used + len(all_results)
    return all_results
