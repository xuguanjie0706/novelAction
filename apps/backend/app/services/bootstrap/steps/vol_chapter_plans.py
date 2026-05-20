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
from app.services.llm_token_budgets import max_tokens_vol_expand_chapters
from app.services.outline_planning import (
    build_book_budget_block,
    chapter_word_budget_for_phase,
    words_to_plan,
)
from app.utils.chapter_numbering import normalize_chapter_plan_title

logger = logging.getLogger(__name__)


# ── 节奏约束（与 vol1 保持一致）─────────────────────────────────────────────

def _get_chapter_phase_guidance(ch_num: int, total: int, phase: str) -> str:
    """按章节区间 + 卷阶段返回细分节奏约束。

    Args:
        ch_num: 当前章节编号（1-based，相对本卷）。
        total:  本卷总章数（30 或 60）。
        phase:  卷级 phase 标记（opening/rising/turning/dark_hour/climax/ending）。

    Returns:
        注入 prompt 的节奏约束文字块；未命中时返回空字符串。
    """
    if phase == "opening":
        if ch_num <= 5:
            return (
                "【开局1-5章·生死钩子区】前500字必须建立主角核心压力/不公正处境；"
                "主角必须在本章内主动采取行动（不是被动等待）；"
                "每章结尾留下读者必须知道答案的具体问题，不能用「主角沉思」收尾。"
            )
        elif ch_num <= 15:
            return (
                "【开局6-15章·金手指起飞区】主角开始展现核心能力，每3章至少1次具体逆转或胜利；"
                "引入第一条感情线/兄弟情，不能只推主线；"
                "开始埋本卷第一条长线伏笔，制造读者期待。"
            )
        elif ch_num <= int(total * 0.75):
            return (
                "【开局中段·扩张铺垫区】势力扩张，主角圈子开始扩大；"
                "引入更大威胁让读者感受到当前成功只是开始；"
                "感情/兄弟线要有实质性推进，不能只是点缀。"
            )
        else:
            return (
                "【开局末段·卷末冲刺区】本卷主线冲突推向高潮，至少1章有爆发点；"
                "留下一个跨卷悬念让读者必须看下一卷；"
                "回收本卷至少1条长线伏笔。"
            )
    elif phase == "rising":
        if ch_num <= int(total * 0.3):
            return (
                "【起飞前段·势力奠基区】主角快速积累资源/盟友，但必须有竞争对手压制节奏；"
                "每3章要有1次主角圈子扩大或实力背书事件；"
                "感情线/兄弟线接入，给读者除「爽」之外的情感出口。"
            )
        elif ch_num <= int(total * 0.7):
            return (
                "【起飞中段·扩张博弈区】主角势力与对立阵营正面接触，输赢都要有代价；"
                "引入「天花板」——让读者感受到主角虽强但还有更高山；"
                "至少1段感情/兄弟线有「差点失去」的险情制造情感张力。"
            )
        else:
            return (
                "【起飞末段·卷末冲刺区】主线矛盾推向本卷顶点，留种子给下卷；"
                "回收本卷至少1条伏笔，兑现本卷开头的至少1个承诺；"
                "最后3章节奏必须明显加速。"
            )
    elif phase == "turning":
        if ch_num <= int(total * 0.4):
            return (
                "【转折前段·代价启动区】主角过去的选择开始反噬，让读者看到「赢是有代价的」；"
                "至少1个之前的盟友/关系出现裂痕或转变；"
                "引入让主角无法用实力直接解决的新困境。"
            )
        else:
            return (
                "【转折后段·两难深化区】矛盾激化到无法回头，主角必须做出无完美解的选择；"
                "伏笔开始密集加热，铺垫至暗期；"
                "每章结尾必须留下「这很可能变得更糟」的预感。"
            )
    elif phase == "dark_hour":
        return (
            "【至暗期·内心突破区】允许虐主，但每次外部失败必须对应主角内心的认知突破；"
            "节奏放缓，强调情感深度而非事件密度——每章1个情感高点比3个情节事件更重要；"
            "这是人物弧度最深刻的阶段：主角的「最大谎言」（错误信念）必须在本阶段被打破；"
            "不要只写外部失败，写主角「看清了什么、接受了什么、放弃了什么」。"
        )
    elif phase == "climax":
        if ch_num <= int(total * 0.4):
            return (
                "【高潮前段·伏笔点燃区】开始密集回收此前埋下的伏笔，让读者感受到「一切都是设计好的」；"
                "主角的成长弧（内在转变）必须在战斗/决策中体现，不只是能力提升；"
                "每章要有1个「啊原来如此」的反转或揭示。"
            )
        else:
            return (
                "【高潮后段·终战收束区】所有主线悬念必须在本段有明确答案（即使留余韵）；"
                "主角的最终胜利必须来自内心成长，不只是境界/外力；"
                "最后3章为下一部/下一阶段留下1颗精准的悬念种子。"
            )
    elif phase == "ending":
        return (
            "【收束期·情感落地区】主线冲突收尾，人物关系有明确落点（成长/改变/和解/死亡）；"
            "节奏逐渐放缓，给读者情感上的「着陆感」，不要虎头蛇尾；"
            "必须留下至少1颗让读者期待下一部的悬念种子；"
            "感情线/兄弟线在本阶段有里程碑性的定格（告白/决裂/和解都算）。"
        )
    return ""


# ── 已写上下文格式化（动态注入，区别于 editorial 静态块）───────────────────

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
        "只返回 JSON 数组，不要任何说明文字。"
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

    batch_ranges = [(1, min(30, planned))]
    if planned > 30:
        batch_ranges.append((31, planned))

    for batch_start, batch_end in batch_ranges:
        batch_count = batch_end - batch_start + 1
        # 上卷 hook 约束只在第一批第一章有意义，后续批次置空避免重复注入
        if batch_start > 1:
            prev_vol_hook_block = ""

        # 批次延续锚：用前批最后4章的「选择代价」驱动下一批开头
        prev_summary = ""
        if all_results:
            anchor_lines: list[str] = []
            for n in all_results[-4:]:
                ex = n.extra or {}
                cost = ex.get("choice_cost", "")
                want = ex.get("protagonist_want", "")
                anchor_lines.append(
                    f"  第{n.sort_order + 1}章：{n.summary or ''}｜主角欲望：{want}｜遗留代价：{cost}"
                )
            prev_summary = (
                "\n【前批末尾4章遗留状态（本批第1章必须直接承接，不能无视这些代价）】\n"
                + "\n".join(anchor_lines)
                + "\n  ⚠️ 本批第1章的 opening_hook 必须让读者感受到上面最后1章的代价仍在发酵。"
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
            "2. choice_cost 不能为空——零代价的选择不是戏剧，必须为下一章留下明确债务\n"
            "3. end_hook 必须具体到手法（「主角打开了一扇他以为已经关闭的门」比「结局悬念」合格）\n"
            "4. villain_action 不能只写「（无）」——反派的独立行动是本书节奏的第二引擎\n"
            "5. core_event 必须是 protagonist_choice 的直接后果，因果链不能断\n"
            "6. storyline_refs 必须交叉出现，主线不能连续 3 章独占（除非 phase=climax 的最后 5 章）\n"
            "7. 本卷内至少 2 条贯穿伏笔线：埋入章写「埋[xxx|主题:yyy]」，推进章写「加热[xxx+手法]」，回收章写「收[xxx]」\n"
            "8. 有未兑现读者承诺（🔴🟠级）的，必须为每条指定具体兑现章节\n"
            "9. has_face_slap 的频率必须符合立项定位的 face_slap_pattern（不能全是 false）\n"
            "10. 若 phase=dark_hour，至少 40% 的章节 has_emotional_beat=true，且 pacing 不得连续 3 章是 fast\n"
            "11. involved_characters 只能使用上方已知人物名，不要发明新名字\n"
            "只返回 JSON 数组，不要任何解释文字。"
        )

        batch_data: list = []
        for gen_attempt in range(2):
            try:
                raw = await svc._call_with_retry(
                    system, prompt, task="bootstrap.vol_chapters",
                    max_tokens=max_tokens_vol_expand_chapters(),
                )
                batch_data = parse_json(raw)
                if not isinstance(batch_data, list):
                    batch_data = batch_data.get("chapters", [])
            except Exception:
                batch_data = []
                break

            actual_count = len(batch_data)
            if actual_count == batch_count:
                break
            if gen_attempt == 0:
                logger.warning(
                    "GEN-01 批次数漂移，重试：期望%d章，实际%d章（卷=%s，批次=%d-%d）",
                    batch_count, actual_count, volume_node.id, batch_start, batch_end,
                )
                continue
            logger.warning(
                "GEN-01 批次数仍不符，截断：期望%d章，实际%d章",
                batch_count, actual_count,
            )
            batch_data = batch_data[:batch_count]

        if not batch_data:
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
            logger.error(
                "章纲被 linter 阻断（卷=%s，已暂存 %d 章草稿）",
                volume_node.id,
                len(all_results),
            )

    # 全书配额计数器累加（供后续卷展开时读取，防止漂移）
    ctx["chapter_quota_used"] = quota_used + len(all_results)

    return all_results
