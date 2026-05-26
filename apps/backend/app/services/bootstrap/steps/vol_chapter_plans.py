"""Bootstrap：任意卷章级大纲（chapter_plan）懒展开。

与 vol1_chapter_plans.py 的核心差异
--------------------------------------
1. 接受任意 volume OutlineNode，不硬编码第一卷。
2. 接受来自 context_vol_expand.build_vol_expand_ctx 的「总编辑级富上下文」：
   - editorial_prompt_block：包含立项定位 / 全卷骨架 / 心理档案 / 关系张力台账 /
     伏笔台账 / 读者承诺欠债 / 反派行动线 / 节奏统计等
   - 三类动态上下文：written_summaries / open_promises / memory_chunks
3. 节奏约束（_get_chapter_phase_guidance）与 vol1 完全一致，复用不另立。

设计原则（继承自 vol1）
-------------------------
章节计划不是「事件清单」，而是「主角欲望→障碍→选择→代价」的因果链。
每章必须回答：主角主动想要什么？什么挡住了他？他做了什么选择（揭示性格）？
这个选择的代价如何喂给下一章？只有这样，章节之间才有真正的叙事张力。
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import OutlineNode, Project
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
from app.utils.chapter_numbering import normalize_chapter_plan_title

logger = logging.getLogger(__name__)

# 节奏约束从共享模块引入
_get_chapter_phase_guidance = get_chapter_phase_guidance


# ── 已写上下文格式化（动态注入，区别于 editorial 静态块）───────────────────

def _fmt_storyline_names_block(storyline_ids_map: dict[str, str]) -> str:
    """生成「精确故事线名称」提示块，防止 AI 返回措辞不一致的名称导致挂线失败。

    AI 看到此块后必须从列表中原词填写 storyline_refs，而不是自由发挥名称。
    """
    if not storyline_ids_map:
        return ""
    names_list = ", ".join(f'"{n}"' for n in storyline_ids_map)
    return (
        f"\n【故事线精确名称（storyline_refs 必须从以下名称中原词选择）】\n"
        f"  可用值：{names_list}\n"
        f"  ⚠️ 不得使用上方故事线块中显示的类型标签（如 main/romance），必须用此处的中文名称。\n"
    )


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


def _fmt_written_summaries(summaries: list[str], max_items: int = 20) -> str:
    """将已写章节摘要压缩为 prompt 块。"""
    if not summaries:
        return ""
    recent = summaries[-max_items:]
    lines = "\n".join(f"    {i + 1}. {s[:130]}" for i, s in enumerate(recent))
    return (
        f"\n【已写章节摘要（最近{len(recent)}章，按时序——本卷必须从此处自然接续）】\n"
        + lines
        + "\n  ⚠️ 本卷第1章的 opening_hook 必须能直接承接上面最后1条摘要的结局状态。"
    )


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

    planned = (volume_node.extra or {}).get("planned_chapters", 30)
    if planned not in (30, 60):
        planned = 30

    # ── 全书预算锚点（ctx 由 gen_volumes 初始化；兜底用 target_words 重算）──────
    tw = int(project.target_words or 1_200_000)
    plan = words_to_plan(tw)
    quota_total = ctx.get("chapter_quota_total", plan["total_chapters"])
    quota_total_volumes = ctx.get("chapter_quota_total_volumes", plan["total_volumes"])
    quota_used = ctx.get("chapter_quota_used", 0)

    genre = ctx.get("genre", project.genre or "玄幻")
    modern_guard = ""
    if is_xuanhuan_like_genre(genre):
        modern_guard = "\n\n" + format_modern_blacklist_for_prompt()

    # ── 系统提示（总编辑级别，明确身份与职责）──────────────────────────────
    system = (
        "你是有30年网络小说从业经验的总编辑，深度参与过数百部上百万字长篇网文的策划。\n"
        "你的职责：为本卷生成章级大纲，每一章都必须是可以直接开写的创作蓝图，\n"
        "而不是模糊的情节清单。你知道：\n"
        "  1. 章节的核心是「主角欲望→障碍→选择→代价」的因果链，不是事件流水账\n"
        "  2. 打脸节奏、感情线密度、反派行动频率必须符合立项定位\n"
        "  3. 每章的 end_hook 决定读者是否点击下一章，废话不合格\n"
        "  4. 伏笔台账和读者承诺是你必须在本卷解决的债务，拖欠就是违约\n"
        "  5. 反派有自己的独立行动线，不是只在主角视角才存在\n"
        "  6. 玄幻/仙侠/古风：禁用现代科技术语与商业话术（如逆向工程、解析改良、畅销榜、算法），"
        "改用辨药、拆方、重配丹纹、坊市热销等世界观内表达\n"
        "只返回 JSON 数组，不要任何说明文字。"
        + modern_guard
    )

    # ── 主角基本信息 ──────────────────────────────────────────────────────────
    protagonist = ctx.get("protagonist", "主角")
    char_profiles = ctx.get("char_profiles", {})

    # 主角心理档案（单独突出）
    protag_psychology = ""
    if protagonist in char_profiles:
        p = char_profiles[protagonist]
        protag_psychology = (
            f"\n【主角「{protagonist}」心理档案（章节行为的底层驱动器，最高优先级约束）】\n"
            f"  境界状态：{p.get('current_realm', '未知')} | 当前位置：{p.get('current_location', '未知')}\n"
            f"  核心恐惧/创伤：{p.get('core_wound', '（未设定）')}\n"
            f"  当前最强欲望：{p.get('current_desire', '（未设定）')}\n"
            f"  价值观：{p.get('values', '（未设定）')}\n"
            f"  人物弧线：{p.get('arc', '（未设定）')}\n"
            f"  未暴露的秘密：{p.get('secrets', '（无）')}\n"
        )

    # 人物阵容概览
    char_lines: list[str] = []
    for name in ctx.get("char_names", []):
        tier = "核心" if name in ctx.get("core_char_names", []) else "配角"
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
    written_block = _fmt_written_summaries(written_summaries)

    all_results: list[OutlineNode] = []
    batch_errors: list[str] = ctx.setdefault("vol_chapter_batch_errors", [])
    char_name_to_id = ctx.get("char_name_to_id", {})
    storyline_ids_map = ctx.get("storyline_ids", {})

    batch_ranges = [(1, min(30, planned))]
    if planned > 30:
        batch_ranges.append((31, planned))

    for batch_start, batch_end in batch_ranges:
        batch_count = batch_end - batch_start + 1
        # 上卷 hook 约束只在第一批第一章有意义，后续批次置空避免重复注入
        if batch_start > 1:
            prev_vol_hook_block = ""

        # 批次延续锚：传入前批完整大纲，确保第31章能真正承接第30章（而非仅看最后4章）
        prev_summary = ""
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
            last_cost = last_ex.get("choice_cost", "") or last_ex.get("end_hook", "") or last.summary or ""
            prev_summary = (
                f"\n【本卷前{len(all_results)}章完整大纲（续写须与之一脉相承）】\n"
                + "\n".join(full_lines)
                + f"\n  ⚠️ 本批第1章（第{batch_start}章）必须直接承接第{len(all_results)}章的结局："
                f"「{last_cost[:120]}」，不得无视这个代价另起炉灶。"
            )

        # 按章节区间注入细分节奏约束
        phase_guidance_lines: list[str] = []
        for ch in range(batch_start, batch_end + 1):
            g = _get_chapter_phase_guidance(ch, planned, volume_node.phase or "rising")
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
            f"  卷末悬念种子：{volume_node.hook or '（未填写）'}\n\n"
            f"## 人物阵容概览\n  {char_snapshot}\n"
            + protag_psychology
            + "\n"
            + editorial_prompt_block  # Tier 1-5 富上下文
            + prev_vol_hook_block     # 卷间衔接：上卷末悬念硬约束（仅第一批有效）
            + written_block           # 动态：已写章节摘要
            + memory_block            # 动态：记忆锚点
            + phase_block             # 节奏约束
            + prev_summary            # 批次延续锚
            + budget_block            # 全书字数预算（防漂移）
            + _fmt_storyline_names_block(storyline_ids_map)  # 精确故事线名映射（供 AI 原词填写）
            + f"\n\n# 生成要求\n"
            f"请为本卷第{batch_start}～{batch_end}章生成{batch_count}个章节计划，返回JSON数组：\n"
            "[\n"
            "  {\n"
            f'    "chapter_number": {batch_start},\n'
            '    "title": "第X章：章节标题（有画面感，≤12字，必须制造期待）",\n'
            '\n'
            '    // ── 欲望-障碍-选择-代价四元组（章节叙事引擎，必须严密因果）──\n'
            '    "protagonist_want": "主角这一章主动想要什么（必须是主动欲望，不是被动应付）",\n'
            '    "protagonist_obstacle": "什么具体阻止了他（内部恐惧或外部冲突，二选一或兼有）",\n'
            '    "protagonist_choice": "他做了什么关键选择（必须暴露性格，不只是解决问题）",\n'
            '    "choice_cost": "这个选择的代价（喂给下一章的债务，不能零代价）",\n'
            '\n'
            '    // ── 章节结构骨架 ──\n'
            '    "opening_hook": "开篇钩子：前500字核心手段（≤30字，必须让读者无法放下第一句）",\n'
            '    "core_event": "核心事件：必须是 protagonist_choice 的直接后果，格式「因[choice]→[result]」（≤60字）",\n'
            '    "character_change": "谁的认知/处境/关系发生了不可逆变化（≤30字，不能只写外部变化）",\n'
            '    "end_hook": "章末钩子：读完最后一句停不下来的原因（≤30字，禁用「悬念丛生」「让读者期待」等废话，必须具体手法）",\n'
            '\n'
            '    // ── 伏笔与承诺管理 ──\n'
            '    "foreshadow": "伏笔操作：埋[伏笔内容|主题:与全书立意的关联] / 收[伏笔代号+内容] / 加热[伏笔代号+推进方式]（无则填空）",\n'
            '    "promise_fulfilled": "本章兑现了哪条读者承诺（填承诺原文片段，无则填空字符串）",\n'
            '\n'
            '    // ── 反派与配角 ──\n'
            '    "villain_action": "反派这一章在做什么（即便不在主角视角），对主角的威胁如何量化？",\n'
            '    "supporting_spotlight": "哪个配角有独立的情节推进（不只是配合主角），填姓名+做了什么",\n'
            '\n'
            '    // ── 节奏与情感标记 ──\n'
            '    "reader_emotion_target": "本章结束时读者的目标情绪（exciting/tense/sad/romantic/mysterious/warm/anxious/epic）",\n'
            '    "involved_characters": ["出场人物名（只用已知人物名）"],\n'
            '    "storyline_refs": ["推进了哪条故事线（从已有故事线选）"],\n'
            '    "pacing": "fast/normal/slow/climax",\n'
            '    "emotional_tone": "exciting/tense/sad/romantic/mysterious/funny/epic/calm",\n'
            '    "power_milestone": "若本章有境界突破/技能习得/法宝获得则描述，否则填空",\n'
            '    "has_face_slap": false,\n'
            '    "has_emotional_beat": false,\n'
            '    "expected_words": 2200\n'
            "  }\n"
            "]\n"
            "（expected_words 参考：opening/ending≈2000-2400，rising≈2300，turning≈2400，"
            "dark_hour≈2600-2800，climax≈3000-3300；fast 节奏-200，slow/climax 节奏+200-500；"
            "有打脸/情感高点+200。请按章节实际情况填写，不要全部填同一个数字。）\n\n"
            "# 编辑铁律（违反任何一条视为不合格输出）\n"
            "1. protagonist_want 必须是「主动欲望」而非「被动应付」——区别：主动=「他想要X」，被动=「他被迫处理Y」\n"
            "2. choice_cost 不能为空字符串——这是最高优先级约束。零代价的选择不是戏剧；"
            "格式示例：「答应了陆青云的条件，但被迫交出了令牌，下章必须面对陆青云派来监视的人」\n"
            "3. 章际因果链（SEQ 约束，必须做到）：第 N+1 章的 opening_hook 必须包含第 N 章 choice_cost "
            "中的关键词或直接后果。示例：上章 choice_cost=「杀了守卫暴露了身份」→ 下章 opening_hook 必须"
            "写「身份暴露后的追捕/盘问场景」，不能无视这个代价直接写新事件。\n"
            "4. end_hook 必须具体到手法（「主角打开了一扇他以为已经关闭的门」比「结局悬念」合格）\n"
            "5. villain_action 不能只写「（无）」——反派的独立行动是本书节奏的第二引擎\n"
            "6. core_event（即 summary）必须是 protagonist_choice 的直接后果，不能为空\n"
            "7. storyline_refs 必须交叉出现，主线不能连续 3 章独占（除非 phase=climax 的最后 5 章）\n"
            "8. 本卷内至少 2 条贯穿伏笔线：埋入章写「埋[xxx|主题:yyy]」，推进章写「加热[xxx+手法]」，回收章写「收[xxx]」\n"
            "9. promise_fulfilled：若本章是某条未兑现承诺的兑现章，必须填写承诺原文中的关键短语（2字以上）；"
            "其余章节填空字符串即可，不要填占位文字如「无」「暂无」。\n"
            "10. has_face_slap 的频率必须符合立项定位的 face_slap_pattern（不能全是 false）\n"
            "11. 若 phase=dark_hour，至少 40% 的章节 has_emotional_beat=true，且 pacing 不得连续 3 章是 fast\n"
            "12. involved_characters 只能使用上方已知人物名，不要发明新名字\n"
            "13. 玄幻/仙侠：core_event/opening_hook 等字段禁止现代 STEM/商业用语"
            "（逆向工程、解析改良、工业化、市场调研、畅销榜等），须用古风修仙表达\n"
            "只返回 JSON 数组，不要任何解释文字。"
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
                batch_errors.append(f"第{batch_start}-{batch_end}章：{err_msg}")
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
                volume_node.phase or "rising", pacing_val, has_slap, has_beat
            )
            expected_words_val = ai_words if isinstance(ai_words, int) and 1500 <= ai_words <= 4000 else dynamic_words
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
                expected_words=expected_words_val,
                sort_order=ch_num - 1,
                extra={
                    "foreshadow": (item.get("foreshadow") or "").strip(),
                    "promise_fulfilled": (item.get("promise_fulfilled") or "").strip(),
                    "end_hook": end_hook_val or "",
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
                },
            )
            svc.db.add(node)
            svc.db.flush()  # 让 node.id 可用，伏笔同步需要引用它
            sync_chapter_foreshadow(svc.db, project.id, node, ch_num)
            all_results.append(node)

    if all_results:
        from app.services.outline_linter.gate import finalize_volume_chapter_commit

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
    ctx["chapter_quota_used"] = quota_used + len(all_results)

    return all_results
