"""Bootstrap：任意卷 chapter_plan 懒展开（欲望→障碍→选择→代价因果链；prompt 见 prompts/vol_chapter_plans_prompt）。"""

from __future__ import annotations

import logging
from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.chapter_plan_batches import (
    chapter_plan_batch_ranges,
    log_chapter_plan_batches,
    normalize_volume_planned_chapters,
)
from app.services.bootstrap.foreshadow_ops import prepare_chapter_foreshadow_for_node
from app.services.bootstrap.foreshadow_sync import sync_chapter_foreshadow
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.phase_guidance import (
    chapter_number_for_batch_item,
    get_chapter_phase_guidance,
)
from app.services.llm_token_budgets import max_tokens_vol_expand_chapters
from app.services.outline_planning import (
    build_book_budget_block,
    chapter_word_budget_for_phase,
    words_to_plan,
)
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
    sanitize_outline_chapter,
)
from app.services.bootstrap.prompts.vol_chapter_plans_prompt import (
    build_carryover_seq_block,
    build_chapter_plan_generation_tail,
    fmt_storyline_names_block,
    fmt_written_summaries,
    plain_chapter_plan_addendum,
)
from app.utils.chapter_numbering import normalize_chapter_plan_title
from app.utils.writing_style import resolve_project_writing_style

logger = logging.getLogger(__name__)

# 节奏约束从共享模块引入
_get_chapter_phase_guidance = get_chapter_phase_guidance


def _resolve_storyline_ids(
    storyline_refs: list[str],
    storyline_ids_map: dict[str, str],
) -> list[str]:
    """将 AI 返回的 storyline_refs 名称列表映射为 DB ID 列表。

    匹配策略（按优先级）：
    1. 精确匹配（大小写敏感）
    2. 精确匹配（忽略首尾空格）
    3. 包含匹配（AI 返回名称包含 DB 名称，或 DB 名称包含 AI 返回名称）
    4. 不匹配则跳过（不产生空字符串）
    """
    resolved: list[str] = []
    for ref in (storyline_refs or []):
        ref_stripped = ref.strip()
        # ① 精确
        if ref_stripped in storyline_ids_map:
            resolved.append(storyline_ids_map[ref_stripped])
            continue
        # ② 模糊：DB 名是 ref 的子串，或 ref 是 DB 名的子串
        matched = None
        for db_name, db_id in storyline_ids_map.items():
            if db_name in ref_stripped or ref_stripped in db_name:
                matched = db_id
                break
        if matched:
            resolved.append(matched)
    return resolved


# ── 主函数 ────────────────────────────────────────────────────────────────────

async def gen_vol_chapter_plans(
    svc: Any,
    project: Project,
    volume_node: OutlineNode,
    ctx: dict,
    written_summaries: list[str] | None = None,
    open_promises: list[dict] | None = None,
    memory_chunks: list[str] | None = None,
    editorial_prompt_block: str = "",
    *,
    chapter_from: int = 1,
    chapter_to: int | None = None,
    seed_nodes: list[OutlineNode] | None = None,
) -> list[OutlineNode]:
    """为任意卷生成章级大纲节点（chapter_plan）并写库。

    Args:
        svc:                   Bootstrap 服务实例（需要 _call_with_retry / db）。
        project:               当前项目模型。
        volume_node:           目标卷 OutlineNode（node_type 必须为 "volume"）。
        ctx:                   总编辑级上下文字典（由 build_vol_expand_ctx 构建）。
        written_summaries:     已写章节的核心事件摘要，按章序排列。
        open_promises:         未兑现的 ReaderPromise 字典列表（在 editorial_prompt_block 里
                               已经有结构化版本，此参数保留供外部直接传入的轻量场景使用）。
        memory_chunks:         项目 MemoryChunk 内容列表（最近 N 条，作为世界状态锚点）。
        editorial_prompt_block: 来自 build_vol_expand_ctx 的富上下文 prompt 块（包含
                               Tier1-5 全部内容）。若为空则退化到轻量模式。
        chapter_from:         本卷从第几章开始生成（补全/番茄开局物化后为 6）。
        chapter_to:           本卷生成到第几章（默认 planned_chapters）。
        seed_nodes:           已存在的 chapter_plan（物化的开局章等），用于批间衔接。

    Returns:
        已落库的 OutlineNode 列表（chapter_plan 类型），按 sort_order 升序。

    Raises:
        ValueError: volume_node.node_type 不是 "volume" 时抛出。
    """
    if volume_node.node_type != "volume":
        raise ValueError(
            f"volume_node.node_type 必须为 'volume'，实际为 '{volume_node.node_type}'"
        )

    # ── 卷间衔接：强制读取上一卷末悬念钩子 ─────────────────────────────────
    # 上一卷的 hook 是编辑层对读者的承诺；第1章前500字必须让读者感受到它仍在发酵。
    prev_vol_hook_block = ""
    if volume_node.sort_order and volume_node.sort_order > 0:
        from app.models import OutlineNode as _ON
        prev_vol = (
            svc.db.query(_ON)
            .filter(
                _ON.project_id == project.id,
                _ON.node_type == "volume",
                _ON.sort_order == volume_node.sort_order - 1,
            )
            .first()
        )
        prev_hook = (prev_vol.hook or "").strip() if prev_vol else ""
        if prev_hook:
            prev_vol_hook_block = (
                f"\n【上卷末悬念钩子（硬性承接约束）】\n"
                f"  上一卷（{prev_vol.title}）末尾留下的悬念种子：\n"
                f"  「{prev_hook}」\n"
                f"  ⚠️ 本卷第1章的 opening_hook 必须在前500字内让读者感受到这个悬念仍在发酵，\n"
                f"  不得另起炉灶或将其当作背景信息一笔带过。\n"
                f"  第1章 choice_cost 中必须包含上卷末事件的直接后遗症。\n"
            )

    written_summaries = written_summaries or []
    open_promises = open_promises or []
    memory_chunks = memory_chunks or []

    planned = normalize_volume_planned_chapters((volume_node.extra or {}).get("planned_chapters", 30))
    chapter_to = chapter_to if chapter_to is not None else planned
    chapter_from = max(1, min(chapter_from, planned))
    chapter_to = max(chapter_from, min(chapter_to, planned))
    seed_count = len(seed_nodes or [])

    # ── 全书预算锚点（ctx 由 gen_volumes 初始化；兜底用 target_words 重算）──────
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    quota_total = ctx.get("chapter_quota_total", plan["total_chapters"])
    quota_total_volumes = ctx.get("chapter_quota_total_volumes", plan["total_volumes"])
    quota_used = ctx.get("chapter_quota_used", 0)

    vol_extra = volume_node.extra if isinstance(volume_node.extra, dict) else {}
    vol_prot_start = (vol_extra.get("protagonist_realm_start") or "").strip()
    vol_prot_end = (vol_extra.get("protagonist_realm_end") or "").strip()
    vol_boss_realm = (vol_extra.get("volume_boss_realm") or "").strip()

    genre = ctx.get("genre", project.genre or "玄幻")
    modern_guard = ""
    if is_xuanhuan_like_genre(genre):
        modern_guard = "\n\n" + format_modern_blacklist_for_prompt()

    # ── 系统提示（总编辑级别，明确身份与职责）──────────────────────────────
    is_fanqie = (ctx.get("positioning") or {}).get("pace_type") == "fast"
    if is_fanqie:
        from app.services.bootstrap.prompts.vol_chapter_fanqie import fanqie_system_prompt
        system = fanqie_system_prompt(modern_guard)
    else:
        system = (
            "你是有30年网络小说从业经验的总编辑，深度参与过数百部上百万字长篇网文的策划。\n"
            "你的职责：为本卷生成章级大纲，每一章都必须是可以直接开写的创作蓝图，\n"
            "而不是模糊的情节清单。你知道：\n"
            "  1. 章节的核心是「主角欲望→障碍→选择→代价」的因果链，不是事件流水账\n"
            "  2. 打脸节奏、感情线密度、反派行动频率必须符合立项定位\n"
            "  3. 每章的 end_hook 决定读者是否点击下一章，废话不合格\n"
            "  4. 伏笔台账和读者承诺是你必须在本卷解决的债务，拖欠就是违约\n"
            "  5. 反派有自己的独立行动线，不是只在主角视角才存在\n"
            "  6. 同一批 JSON 内：第 N+1 章 opening_hook 必须先承接第 N 章 choice_cost（与 linter SEQ-01 同规则，"
            "须含代价原文≥2连续汉字，禁止仅靠主角名蹭字）\n"
            "  7. 玄幻/仙侠/古风：禁用现代科技术语与商业话术（如逆向工程、解析改良、畅销榜、算法），"
            "改用辨药、拆方、重配丹纹、坊市热销等世界观内表达\n"
            "只返回 JSON 数组，不要任何说明文字。"
            + modern_guard
        )

    # 白话直白（番茄纯爽文）：章纲层即要求稀疏、单事件、直给钩子（prompt 见 prompts 模块）
    if resolve_project_writing_style(project) == "plain":
        system += plain_chapter_plan_addendum()

    # ── 主角基本信息 ──────────────────────────────────────────────────────────
    protagonist = ctx.get("protagonist", "主角")
    char_profiles = ctx.get("char_profiles", {})

    # 主角心理档案（单独突出）
    protag_psychology = ""
    if protagonist in char_profiles:
        p = char_profiles[protagonist]
        if vol_prot_start or vol_prot_end:
            realm_state = (
                f"{vol_prot_start} → 本卷目标 {vol_prot_end}"
                if vol_prot_start and vol_prot_end
                else (vol_prot_end or vol_prot_start)
            )
        else:
            realm_state = p.get("current_realm", "未知")
        protag_psychology = (
            f"\n【主角「{protagonist}」心理档案（章节行为的底层驱动器，最高优先级约束）】\n"
            f"  境界状态：{realm_state} | 当前位置：{p.get('current_location', '未知')}\n"
            f"  核心恐惧/创伤：{p.get('core_wound', '（未设定）')}\n"
            f"  当前最强欲望：{p.get('current_desire', '（未设定）')}\n"
            f"  价值观：{p.get('values', '（未设定）')}\n"
            f"  人物弧线：{p.get('arc', '（未设定）')}\n"
            f"  未暴露的秘密：{p.get('secrets', '（无）')}\n"
        )
        if vol_prot_end:
            protag_psychology += (
                f"  ⚠️ 本卷末主角须达到「{vol_prot_end}」；"
                f"章纲 power_milestone 须在本卷内合理分配突破节点，禁止卷末仍停留在卷初境界。\n"
            )
        if vol_boss_realm:
            protag_psychology += (
                f"  ⚠️ 当卷 BOSS 境界「{vol_boss_realm}」；"
                f"对决章节主角 effective 境界须接近卷末目标，禁止 rank 差距超过 2 档。\n"
            )

    # 人物阵容概览
    char_lines: list[str] = []
    for name in ctx.get("char_names", []):
        tier = "核心" if name in ctx.get("core_char_names", []) else "配角"
        if name == protagonist and (vol_prot_start or vol_prot_end):
            realm = (
                f"{vol_prot_start}→{vol_prot_end}"
                if vol_prot_start and vol_prot_end
                else (vol_prot_end or vol_prot_start)
            )
        else:
            realm = ctx.get("char_realms", {}).get(name, "")
        profile = char_profiles.get(name, {})
        status = profile.get("current_status", "alive")
        status_str = "" if status == "alive" else f"·{status}"
        char_lines.append(f"{name}({tier},{realm}{status_str})")
    char_snapshot = "、".join(char_lines)

    # ── 记忆片段块（世界状态锚点）────────────────────────────────────────────
    memory_block = ""
    if memory_chunks:
        mem_lines = "\n".join(f"  • {c[:100]}" for c in memory_chunks[:12])
        memory_block = (
            "\n【关键记忆条目（世界状态锚点，生成时不得与之矛盾）】\n"
            + mem_lines
        )

    # ── 已写上下文 ────────────────────────────────────────────────────────────
    written_block = fmt_written_summaries(written_summaries)

    all_results: list[OutlineNode] = list(seed_nodes or [])
    batch_errors: list[str] = ctx.setdefault("vol_chapter_batch_errors", [])
    char_name_to_id = ctx.get("char_name_to_id", {})
    storyline_ids_map = ctx.get("storyline_ids", {})

    completion_budget = max_tokens_vol_expand_chapters()
    batch_ranges = chapter_plan_batch_ranges(planned, completion_budget)
    batch_ranges = [
        (max(batch_start, chapter_from), min(batch_end, chapter_to))
        for batch_start, batch_end in batch_ranges
        if batch_end >= chapter_from and batch_start <= chapter_to
    ]
    log_chapter_plan_batches(
        logger,
        tag="vol_chapters",
        planned=planned,
        ranges=batch_ranges,
        max_completion_tokens=completion_budget,
    )

    for batch_start, batch_end in batch_ranges:
        batch_count = batch_end - batch_start + 1
        # 上卷 hook 约束只在第一批第一章有意义，后续批次置空避免重复注入
        if batch_start > 1:
            prev_vol_hook_block = ""

        # 批次延续锚：传入前批完整大纲，确保第31章能真正承接第30章（而非仅看最后4章）
        prev_summary = ""
        last_batch_tail_cost = ""
        if all_results:
            full_lines: list[str] = []
            for n in all_results:
                ex = n.extra or {}
                cost = ex.get("choice_cost", "")
                end_hook = ex.get("end_hook", "")
                want = ex.get("protagonist_want", "")
                ch_num = n.sort_order + 1
                # 紧凑单行：章号+标题+情感基调+摘要+代价/钩子
                tail = cost or end_hook
                full_lines.append(
                    f"  第{ch_num}章《{n.title or ''}》"
                    f"{('[' + n.emotional_tone + ']') if n.emotional_tone else ''}"
                    f"  {n.summary or ''}｜欲望：{want}｜代价/钩子：{tail}"
                )
            last = all_results[-1]
            last_ex = last.extra or {}
            last_batch_tail_cost = (
                last_ex.get("choice_cost", "")
                or last_ex.get("end_hook", "")
                or last.summary
                or ""
            )
            prev_summary = (
                f"\n【本卷前{len(all_results)}章完整大纲（续写须与之一脉相承）】\n"
                + "\n".join(full_lines)
                + f"\n  ⚠️ 本批第1章（第{batch_start}章）必须直接承接第{len(all_results)}章的结局："
                f"「{last_batch_tail_cost[:120]}」，不得无视这个代价另起炉灶。"
            )

        carryover_block = build_carryover_seq_block(
            batch_start=batch_start,
            batch_end=batch_end,
            last_batch_tail_cost=last_batch_tail_cost,
            protagonist_name=protagonist,
        )

        # 按章节区间注入细分节奏约束
        phase_guidance_lines: list[str] = []
        for ch in range(batch_start, batch_end + 1):
            g = _get_chapter_phase_guidance(
                ch, planned, volume_node.phase or "rising", is_fanqie=is_fanqie,
            )
            if g and g not in phase_guidance_lines:
                phase_guidance_lines.append(g)
        phase_block = ""
        if phase_guidance_lines:
            phase_block = "\n【本批节奏约束（按章节区间——必须严格执行）】\n" + "\n".join(
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

        from app.services.bootstrap.volume_beats import build_volume_beat_expand_block
        from app.services.bootstrap.storyline_weave_blocks import build_volume_storyline_weave_block

        volume_beat_block = build_volume_beat_expand_block(
            volume_node, batch_start, batch_end,
        )
        storyline_weave_block = build_volume_storyline_weave_block(
            svc.db,
            str(project.id),
            volume_node.sort_order or 0,
            planned,
        )

        opening_contract_block = ""
        if (volume_node.sort_order or 0) == 0 and batch_start <= 10:
            from app.services.ai.opening_contract_context import (
                build_opening_contract_expand_block,
            )

            _oc = ctx.get("opening_contract") or (
                (project.extra or {}).get("opening_contract") if project.extra else {}
            )
            if isinstance(_oc, dict) and _oc:
                opening_contract_block = build_opening_contract_expand_block(
                    _oc,
                    batch_start,
                    batch_end,
                    vol1_summary=volume_node.summary or "",
                    vol1_conflict=volume_node.conflict or "",
                    vol1_hook=volume_node.hook or "",
                )

        # ── 完整 prompt 拼装 ──────────────────────────────────────────────────
        prompt = (
            f"# 创作任务：《{ctx.get('project_title', project.title)}》{volume_node.title}\n\n"
            f"主角：{protagonist}  |  风格类型：{ctx.get('genre', '玄幻')}\n"
            f"一句话创意：{ctx.get('logline', project.logline or '')}\n"
            f"立意：{(ctx.get('premise', project.premise or ''))[:300] or '（未填写）'}\n\n"
            f"## 本卷基本信息\n"
            f"  卷名：{volume_node.title}\n"
            f"  phase：{volume_node.phase}（{planned}章）\n"
            f"  卷摘要：{volume_node.summary or '（未填写）'}\n"
            f"  核心冲突：{volume_node.conflict or '（未填写）'}\n"
            f"  卷末悬念种子：{volume_node.hook or '（未填写）'}\n"
            f"  卷末高潮摘要：{volume_node.highlight or '（见导演单 volume_climax）'}\n"
            + (
                f"  主角境界路线：{vol_prot_start} → {vol_prot_end}\n"
                if vol_prot_start and vol_prot_end
                else (
                    f"  主角卷末目标境界：{vol_prot_end}\n" if vol_prot_end else ""
                )
            )
            + (f"  当卷 BOSS 境界：{vol_boss_realm}\n" if vol_boss_realm else "")
            + "\n"
            f"## 人物阵容概览\n  {char_snapshot}\n"
            + protag_psychology
            + "\n"
            + editorial_prompt_block  # Tier 1-5 富上下文
            + volume_beat_block       # 卷级燃点/高潮节拍
            + storyline_weave_block   # 故事线织网：本卷各线节拍与交叉
            + opening_contract_block  # 第一卷前10章：开局承诺硬对齐
            + prev_vol_hook_block     # 卷间衔接：上卷末悬念硬约束（仅第一批有效）
            + written_block           # 动态：已写章节摘要
            + memory_block            # 动态：记忆锚点
            + phase_block             # 节奏约束
            + prev_summary            # 批次延续锚
            + carryover_block         # SEQ-01 章际衔接（本批内 + 跨批首章）
            + budget_block            # 全书字数预算（防漂移）
            + fmt_storyline_names_block(storyline_ids_map)  # 精确故事线名映射（供 AI 原词填写）
            + build_chapter_plan_generation_tail(
                batch_start=batch_start,
                batch_end=batch_end,
                batch_count=batch_count,
                is_fanqie=is_fanqie,
            )
        )

        batch_data: list = []
        raw = ""
        for gen_attempt in range(2):
            try:
                raw = await svc._call_with_retry(
                    system, prompt, task="bootstrap.vol_chapters",
                    max_tokens=max_tokens_vol_expand_chapters(),
                )
                batch_data = parse_json(raw)
                if not isinstance(batch_data, list):
                    batch_data = batch_data.get("chapters", [])
            except Exception as exc:
                err_msg = str(exc).strip() or type(exc).__name__
                logger.warning(
                    "vol_chapters JSON 解析/调用失败 project=%s volume=%s "
                    "batch=%d-%d attempt=%d: %s; raw_tail=%r",
                    project.id,
                    volume_node.id,
                    batch_start,
                    batch_end,
                    gen_attempt + 1,
                    exc,
                    (raw or "")[-500:],
                )
                batch_data = []
                if gen_attempt == 0:
                    continue
                batch_errors.append(f"第{batch_start}-{batch_end}章：{err_msg}")
                break

            actual_count = len(batch_data)
            if actual_count == batch_count:
                break
            if gen_attempt == 0:
                logger.warning(
                    "GEN-01 批次数漂移，重试：期望%d章，实际%d章（project=%s 卷=%s 批次=%d-%d）",
                    batch_count,
                    actual_count,
                    project.id,
                    volume_node.id,
                    batch_start,
                    batch_end,
                )
                continue
            logger.warning(
                "GEN-01 批次数仍不符，截断：期望%d章，实际%d章（project=%s 卷=%s 批次=%d-%d）",
                batch_count,
                actual_count,
                project.id,
                volume_node.id,
                batch_start,
                batch_end,
            )
            batch_data = batch_data[:batch_count]

        if not batch_data:
            batch_tag = f"第{batch_start}-{batch_end}章"
            if not any(batch_tag in e for e in batch_errors):
                batch_errors.append(f"{batch_tag}：模型未返回可解析的章纲 JSON")
            logger.warning(
                "vol_chapters 批次无有效章纲，已跳过 project=%s volume=%s "
                "batch=%d-%d planned=%d accumulated=%d",
                project.id,
                volume_node.id,
                batch_start,
                batch_end,
                planned,
                len(all_results),
            )
            continue

        for batch_index, item in enumerate(batch_data):
            if isinstance(item, dict):
                item = sanitize_outline_chapter(item, genre)
            ch_num = chapter_number_for_batch_item(batch_start, batch_index, item)
            involved_ids = [
                char_name_to_id[n]
                for n in item.get("involved_characters", [])
                if n in char_name_to_id
            ]
            sl_ids = _resolve_storyline_ids(
                item.get("storyline_refs", []),
                storyline_ids_map,
            )
            end_hook_val = (item.get("end_hook") or "").strip() or None
            pacing_val = item.get("pacing", "normal")
            has_slap = bool(item.get("has_face_slap", False))
            has_beat = bool(item.get("has_emotional_beat", False))
            # AI 给出的 expected_words 优先，动态预算函数做兜底
            ai_words = item.get("expected_words")
            dynamic_words = chapter_word_budget_for_phase(
                volume_node.phase or "rising", pacing_val, has_slap, has_beat,
                is_fanqie=is_fanqie,
            )
            expected_words_val = ai_words if isinstance(ai_words, int) and 1500 <= ai_words <= 4000 else dynamic_words
            fs_ops, fs_laid, fs_resolved, _ = prepare_chapter_foreshadow_for_node(item)
            node = OutlineNode(
                project_id=project.id,
                parent_id=volume_node.id,
                node_type="chapter_plan",
                title=normalize_chapter_plan_title(ch_num, item.get("title")),
                summary=item.get("core_event") or item.get("summary"),
                conflict=item.get("character_change") or item.get("conflict"),
                hook=(item.get("opening_hook") or "").strip() or None,
                highlight=end_hook_val,
                phase=volume_node.phase,
                pacing=pacing_val,
                emotional_tone=item.get("emotional_tone"),
                power_milestone=item.get("power_milestone") or None,
                involved_character_ids=involved_ids,
                storyline_ids=sl_ids,
                foreshadows_laid=fs_laid or None,
                foreshadows_resolved=fs_resolved or None,
                expected_words=expected_words_val,
                sort_order=ch_num - 1,
                extra=_build_chapter_extra(item, is_fanqie),
            )
            svc.db.add(node)
            svc.db.flush()  # 让 node.id 可用，伏笔同步需要引用它
            sync_chapter_foreshadow(svc.db, project.id, node, ch_num)
            all_results.append(node)

    if all_results:
        from sqlalchemy.orm.attributes import flag_modified

        from app.services.outline_linter.gate import finalize_volume_chapter_commit

        vol_extra = dict(volume_node.extra or {})
        vol_extra["expand_batch_starts"] = [
            start for start, _ in batch_ranges if start > 1
        ]
        volume_node.extra = vol_extra
        flag_modified(volume_node, "extra")

        finalize_volume_chapter_commit(
            svc, project, volume_node, all_results, ctx=ctx,
        )
        if ctx.get("linter_blocked"):
            block_payload = ctx.get("linter_block_payload") or {}
            logger.error(
                "GEN-02 章纲被 linter 阻断 project=%s volume=%s chapters=%d rules=%s",
                project.id,
                volume_node.id,
                len(all_results),
                block_payload.get("linter_blocking_rules"),
            )

    if len(all_results) < planned:
        logger.warning(
            "vol_chapters 章纲不完整 project=%s volume=%s 期望=%d 实际=%d linter_blocked=%s",
            project.id,
            volume_node.id,
            planned,
            len(all_results),
            bool(ctx.get("linter_blocked")),
        )
    elif not all_results:
        logger.error(
            "vol_chapters 未生成任何章纲 project=%s volume=%s planned=%d",
            project.id,
            volume_node.id,
            planned,
        )
    else:
        logger.info(
            "vol_chapters 完成 project=%s volume=%s chapters=%d linter_blocked=%s",
            project.id,
            volume_node.id,
            len(all_results),
            bool(ctx.get("linter_blocked")),
        )

    # 全书配额计数器累加（供后续卷展开时读取，防止漂移）
    ctx["chapter_quota_used"] = quota_used + max(0, len(all_results) - seed_count)

    return all_results


def _build_chapter_extra(item: dict, is_fanqie: bool) -> dict:
    """构建 OutlineNode.extra，番茄模式时追加爽感字段。"""
    fs_ops, _, _, foreshadow_legacy = prepare_chapter_foreshadow_for_node(item)
    base = {
        "foreshadow": foreshadow_legacy,
        "foreshadow_ops": fs_ops,
        "promise_fulfilled": (item.get("promise_fulfilled") or "").strip(),
        "end_hook": (item.get("end_hook") or "").strip(),
        "has_face_slap": item.get("has_face_slap", False),
        "has_emotional_beat": item.get("has_emotional_beat", False),
        "protagonist_want": (item.get("protagonist_want") or "").strip(),
        "protagonist_obstacle": (item.get("protagonist_obstacle") or "").strip(),
        "protagonist_choice": (item.get("protagonist_choice") or "").strip(),
        "choice_cost": (item.get("choice_cost") or "").strip(),
        "villain_action": (item.get("villain_action") or "").strip(),
        "supporting_spotlight": (item.get("supporting_spotlight") or "").strip(),
        "reader_emotion_target": (item.get("reader_emotion_target") or "").strip(),
        "bootstrap_generated": False,
        "lazy_expanded": True,
        "storyline_beat_ref": (item.get("storyline_beat_ref") or "").strip(),
    }
    if is_fanqie:
        base.update({
            "satisfaction_setup": (item.get("satisfaction_setup") or "").strip(),
            "satisfaction_payoff": (item.get("satisfaction_payoff") or "").strip(),
            "satisfaction_type": item.get("satisfaction_type") or None,
            "next_chapter_bait": (item.get("next_chapter_bait") or "").strip(),
            "face_slap_target": item.get("face_slap_target") or None,
            "face_slap_audience": (item.get("face_slap_audience") or "").strip(),
            "completion_risk": (item.get("completion_risk") or "").strip(),
        })
    return base
