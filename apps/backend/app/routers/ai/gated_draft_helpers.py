"""
gated_draft_helpers.py — 门控写作辅助函数（上下文构建 / 存库 / 预警格式化）

资源边界：
  本模块仅保留**无业务决策**的纯辅助函数，供 gated_draft_routes.py 和
  pre_write_for_draft.py 共用。不包含 endpoint handler 或质检判断逻辑。

包含函数：
  - _count_words_plain      — 中文字数统计
  - _persist_pre_write_warning_record — 写前预警落库
  - _run_pre_write_warning_inline     — 门控内联写前预警（不走 HTTP）
  - _build_pre_warn_prompt_block      — 预警结果格式化为 prompt 块
  - _build_location_context           — 空间连续性约束块（按角色 current_location 汇总）
  - _build_single_location_block      — 单场感官基准约束块（按 location_id 或 location_name 匹配）
  - _plain_text_from_html             — HTML → 纯文本
  - _save_chapter_content             — 保存章节正文 + ChapterVersion 快照
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import (
    Chapter,
    ChapterVersion,
    Character,
    Foreshadow,
    Location,
    OutlineNode,
    PreWriteWarningRecord,
    Project,
)
from app.routers.chapter_helpers import chapter_has_snapshot_worthy_content
from app.services.ai_service import AIService
from app.services.rag_retrieval_service import (
    client_snapshot_from_log,
    retrieve_and_log_pre_write_memory,
)


def _count_words_plain(text: str) -> int:
    """简易中文字数统计（去 HTML 标签）。"""
    clean = re.sub(r"<[^>]+>", "", text or "")
    chinese = len(re.findall(r"[一-鿿]", clean))
    english = len(re.findall(r"[a-zA-Z]+", clean))
    return chinese + english


def _persist_pre_write_warning_record(
    db: Session,
    *,
    project: Project,
    chapter: Chapter,
    chapter_plan_summary: str,
    model_profile: str,
    llm_provider_id: str | None,
    result: dict,
) -> PreWriteWarningRecord:
    """门控/HTTP 写前预警共用落库，供写作侧栏 history 查阅。"""
    ch_no = chapter.sort_order or 0
    profile = model_profile if model_profile in ("local", "gemini") else "local"
    rec = PreWriteWarningRecord(
        project_id=project.id,
        chapter_id=chapter.id,
        chapter_number=ch_no,
        chapter_plan_summary=chapter_plan_summary or "",
        model_profile=profile,
        llm_provider_id=llm_provider_id,
        result=result,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


async def _run_pre_write_warning_inline(
    db: Session,
    chapter: Chapter,
    project: Project,
    project_id: str,
    svc: AIService,
) -> dict:
    """
    在门控写作开始前内联执行写前预警，不走 HTTP 路由。

    组装与 quality_routes.pre_write_warning 端点相同的上下文（记忆/伏笔/人物/境界），
    调用 AIService.pre_write_warning，返回结果 dict（含 protagonist_fact_sheet /
    writing_brief / must_events / hallucination_traps / risks / reminders）。

    @param db: SQLAlchemy Session
    @param chapter: 已加载的 Chapter 对象
    @param project: 已加载的 Project 对象
    @param project_id: 项目 UUID 字符串
    @param svc: 已初始化的 AIService 实例
    @returns (pre_write_warning 结果 dict, 本次使用的 chapter_plan_summary)
    @raises Exception: AI 调用失败时向上抛出
    """
    # 记忆：用章节 outline 摘要做语义检索，优先拉与本章相关的记忆；
    # max_chapter=chapter.sort_order 防伏笔泄漏；semantic_search 内部已有时序兜底。
    _outline_node = None
    if chapter.outline_node_id:
        from app.models import OutlineNode as _OutlineNode
        _outline_node = db.query(_OutlineNode).filter(
            _OutlineNode.id == chapter.outline_node_id
        ).first()
    _warn_query = " ".join(filter(None, [
        _outline_node.summary if _outline_node else None,
        _outline_node.conflict if _outline_node else None,
    ])) or chapter.title or ""
    _rag_log = None
    if _warn_query:
        _raw_mems, _rag_log = await retrieve_and_log_pre_write_memory(
            db,
            project_id=project_id,
            chapter_id=chapter.id,
            query=_warn_query,
            top_k=40,
            max_chapter=chapter.sort_order,
            commit=True,
        )
    else:
        _raw_mems = []
    memory_chunks = [
        {"title": m.title or "", "content": m.content or "", "memory_type": m.memory_type or "event"}
        for m in _raw_mems
    ]

    # 未回收伏笔
    open_foreshadows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id, Foreshadow.status == "open")
        .order_by(Foreshadow.priority.desc())
        .limit(30)
        .all()
    )
    foreshadow_lines = []
    ch_no = chapter.sort_order or 0
    for f in open_foreshadows:
        code = f.code or "—"
        overdue = "【⚠️已逾期】" if (f.planned_resolve_chapter and ch_no > 0 and f.planned_resolve_chapter <= ch_no) else ""
        foreshadow_lines.append(
            f"{overdue}{code} {f.title or ''} | 预计第{f.planned_resolve_chapter or '?'}章回收 | {(f.description or '')[:100]}"
        )
    foreshadow_ledger = "\n".join(foreshadow_lines)

    # 人物状态（含技能/道具）
    characters = db.query(Character).filter(Character.project_id == project_id).all()

    def _names_brief(lst, key: str) -> str:
        if not lst:
            return ""
        return "、".join(
            (x.get(key, "") if isinstance(x, dict) else str(x))
            for x in lst[:6] if x
        )

    char_lines = []
    for c in characters[:12]:
        line = f"{c.name}：境界={c.current_realm or '?'}，位置={c.current_location or '?'}，状态={c.current_status or 'alive'}"
        sk = _names_brief(c.known_skills, "skill_name")
        if sk:
            line += f"，技能=[{sk}]"
        it = _names_brief(c.owned_items, "item_name")
        if it:
            line += f"，持有=[{it}]"
        char_lines.append(line)
    character_states = "\n".join(char_lines)

    # 境界体系（多轴全保真）
    from app.services.bootstrap.power_registry import build_draft_power_context_from_db

    power_systems_summary = build_draft_power_context_from_db(db, project_id)

    # 大纲五要素
    outline_context = ""
    phase = ""
    outline_node: OutlineNode | None = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(OutlineNode.id == chapter.outline_node_id).first()
        if outline_node:
            parts = []
            if outline_node.summary:
                parts.append(f"概述：{outline_node.summary}")
            if outline_node.hook:
                parts.append(f"开篇钩子：{outline_node.hook}")
            if outline_node.conflict:
                parts.append(f"核心冲突：{outline_node.conflict}")
            if outline_node.highlight:
                parts.append(f"章末方向：{outline_node.highlight}")
            if outline_node.power_milestone:
                parts.append(f"实力里程碑：{outline_node.power_milestone}")
            if outline_node.emotional_tone:
                parts.append(f"情感基调：{outline_node.emotional_tone}")
            outline_context = "\n".join(parts)
            phase = getattr(outline_node, "phase", None) or (outline_node.extra or {}).get("phase") or ""
    if not phase and outline_node and outline_node.parent_id:
        vol = db.query(OutlineNode).filter(OutlineNode.id == outline_node.parent_id).first()
        if vol:
            phase = getattr(vol, "phase", None) or (vol.extra or {}).get("phase") or ""

    # 连续性账本
    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    continuity_state = str(story_core.get("rolling_continuity_state", ""))

    # 大纲五要素兜底（无 outline_node 时用章节标题）
    chapter_plan_summary = outline_context or f"第{chapter.sort_order or '?'}章《{chapter.title}》"

    # 开篇衔接技法菜单：从角色位置记录 + 大纲里程碑推导，注入 pre_write_warning
    # 让"30年主编"AI 按技法菜单给出可执行的 transition_directive
    from app.services.ai.transition_advisor import build_transition_menu_block
    _primary_char = characters[0] if characters else None
    _db_location = (_primary_char.current_location or "").strip() if _primary_char else ""
    _power_milestone = (outline_node.power_milestone or "").strip() if outline_node else ""
    transition_menu = build_transition_menu_block(
        db_location=_db_location,
        outline_power_milestone=_power_milestone,
    )

    result = await svc.pre_write_warning(
        project_title=project.title,
        genre=project.genre or "玄幻",
        chapter_plan_summary=chapter_plan_summary,
        memory_chunks=memory_chunks,
        continuity_state=continuity_state,
        foreshadow_ledger=foreshadow_ledger,
        character_states=character_states,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        phase=phase,
        transition_menu=transition_menu,
    )
    if _rag_log is not None:
        result = dict(result)
        result["rag_retrieval_log_id"] = str(_rag_log.id)
        result["rag_context"] = client_snapshot_from_log(_rag_log)
    return result, chapter_plan_summary


def _build_pre_warn_prompt_block(warn_result: dict) -> str:
    """
    将写前预警结果格式化为注入首次起笔 prompt 的「写前简报」块。

    不重复向 AI 展示完整的 JSON，只提取对写正文最关键的信息：
    - 主角状态锁定（protagonist_fact_sheet）
    - 本章写法简报（writing_brief）
    - 必发事件（must_events）
    - 幻觉预防清单（hallucination_traps）
    - 高危/中危风险（risks severity>=medium）

    @param warn_result: pre_write_warning 返回的 dict
    @returns 格式化文本块（用于拼入 user_prompt）
    """
    lines: list[str] = ["\n\n===【写前简报（由30年主编生成，写正文时必须严格遵守）】==="]

    # ① 主角状态锁定
    pfs = warn_result.get("protagonist_fact_sheet") or {}
    if isinstance(pfs, dict):
        lines.append("\n▍主角状态锁定（本章开笔时的精确状态，不得幻觉升级或改动）")
        if pfs.get("realm"):
            lines.append(f"  境界：{pfs['realm']}")
        if pfs.get("location"):
            lines.append(f"  位置：{pfs['location']}")
        if pfs.get("key_skills"):
            lines.append("  本章可用技能：" + "；".join(pfs["key_skills"][:5]))
        if pfs.get("key_items"):
            lines.append("  持有道具：" + "；".join(pfs["key_items"][:5]))
        if pfs.get("forbidden"):
            lines.append("  ⛔ 本章禁止出现：" + "；".join(pfs["forbidden"][:5]))

    # ② 本章写作简报
    wb = warn_result.get("writing_brief") or {}
    if isinstance(wb, dict) and any(wb.values()):
        lines.append("\n▍本章写作指导")
        if wb.get("opening_strategy"):
            lines.append(f"  开篇策略：{wb['opening_strategy']}")
        if wb.get("conflict_structure"):
            lines.append(f"  冲突节拍：{wb['conflict_structure']}")
        if wb.get("closing_hook"):
            lines.append(f"  章末钩子：{wb['closing_hook']}")
        if wb.get("word_rhythm"):
            lines.append(f"  字数节奏：{wb['word_rhythm']}")

    # ③ 必发事件
    must_events = warn_result.get("must_events") or []
    if must_events:
        lines.append("\n▍本章必须发生的事件（逐条落实，不得遗漏）")
        for i, ev in enumerate(must_events[:4], 1):
            lines.append(f"  {i}. {ev}")

    # ④ 幻觉预防
    traps = warn_result.get("hallucination_traps") or []
    if traps:
        lines.append("\n▍常见幻觉预防（逐条注意）")
        for trap in traps[:5]:
            lines.append(f"  • {trap}")

    # ⑤ 高危/中危风险
    risks = [r for r in (warn_result.get("risks") or []) if r.get("severity") in ("high", "critical", "medium")]
    if risks:
        lines.append("\n▍需处理的风险（severity medium/high/critical）")
        for r in risks[:5]:
            lines.append(f"  [{r.get('severity','?')}·{r.get('type','?')}] {r.get('description','')}")
            if r.get("suggested_fix"):
                lines.append(f"    建议：{r['suggested_fix']}")

    # ⑥ 开篇衔接策略（transition_directive）——空间衔接 + 破境衔接
    td = warn_result.get("transition_directive") or {}
    sb = td.get("spatial_bridge") or {}
    rb = td.get("realm_bridge") or {}
    has_spatial = isinstance(sb, dict) and sb.get("needed") and sb.get("instruction")
    has_realm = isinstance(rb, dict) and rb.get("needed") and rb.get("instruction")
    if has_spatial or has_realm:
        lines.append("\n▍⚡ 开篇衔接策略（AI 必须按此执行，不得随意省略或替换）")
        if has_spatial:
            lines.append(
                f"  【空间衔接·{sb.get('technique_name','?')}】\n"
                f"  {sb['instruction']}"
            )
        if has_realm:
            lines.append(
                f"  【破境衔接·{rb.get('technique_name','?')}】\n"
                f"  {rb['instruction']}"
            )

    lines.append("===")
    return "\n".join(lines)


def _build_location_context(db: Session, project_id: str) -> str:
    """
    构造空间连续性约束块，注入写章 prompt。

    逻辑：
    1. 查询项目内所有 Character（最多 12 个）的 current_location 字段；
    2. 对每个非空 current_location，尝试在 locations 表中按名称/别名模糊匹配；
    3. 若匹配到 Location，提取 danger_level + sensory_signature 作为感官基准；
    4. 组装成「⚠️ 空间连续性约束」块，写章时 AI 必须遵守。

    空返回值（空字符串）：项目无角色、所有角色位置为空，或数据库中无任何 Location 记录时返回 ""。

    @param db: SQLAlchemy Session
    @param project_id: 项目 UUID 字符串
    @returns 格式化约束文本块；无有效数据时返回空字符串
    """
    characters = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.realm_rank.desc().nullslast())  # 主角/高境界角色优先
        .limit(12)
        .all()
    )

    char_locs: list[tuple[str, str]] = [
        (c.name, (c.current_location or "").strip())
        for c in characters
        if (c.current_location or "").strip()
    ]
    if not char_locs:
        return ""

    # 预加载项目内所有 Location，用于名称匹配（数量通常 < 100，全量拉取可接受）
    all_locations = (
        db.query(Location)
        .filter(Location.project_id == project_id)
        .all()
    )

    def _match_location(loc_text: str) -> Location | None:
        """按精确名 → 别名包含 → 名称包含的优先级依次匹配。"""
        loc_lower = loc_text.lower()
        for loc in all_locations:
            if loc.name.lower() == loc_lower:
                return loc
        for loc in all_locations:
            aliases = loc.aliases or []
            if any(a.lower() == loc_lower for a in aliases):
                return loc
        for loc in all_locations:
            if loc.name.lower() in loc_lower or loc_lower in loc.name.lower():
                return loc
        return None

    danger_labels = {
        "safe": "安全",
        "neutral": "中性",
        "dangerous": "危险",
        "forbidden": "禁区",
    }

    # 按展示地点合并多人：「张三、李四所在：」+ 同一条地点/感官行，避免重复块浪费上下文。
    groups: dict[str, dict] = {}
    group_order: list[str] = []

    for char_name, loc_text in char_locs:
        matched = _match_location(loc_text)
        loc_display = matched.name if matched else loc_text
        danger = ""
        sensory = ""
        if matched:
            danger = f"危险等级：{danger_labels.get(matched.danger_level or 'neutral', matched.danger_level)}"
            sensory = (matched.sensory_signature or "").strip()

        entry_key = loc_display.lower()
        if entry_key not in groups:
            groups[entry_key] = {
                "names": [char_name],
                "loc_display": loc_display,
                "danger": danger,
                "sensory": sensory,
            }
            group_order.append(entry_key)
        else:
            groups[entry_key]["names"].append(char_name)

    lines: list[str] = []
    for entry_key in group_order:
        g = groups[entry_key]
        names_joined = "、".join(g["names"])
        loc_line = f"  - {g['loc_display']}" + (f"（{g['danger']}）" if g["danger"] else "")
        if g["sensory"]:
            loc_line += f"\n    感官基准：{g['sensory']}"
        lines.append(f"{names_joined}所在：\n{loc_line}")

    if not lines:
        return ""

    block = (
        "【⚠️ 空间连续性约束（必须遵守）】\n"
        "本章起始空间状态（来自上章复盘提取）：\n"
        + "\n".join(lines)
        + "\n⚠️ 严禁在未交代过渡（如传送/赶路场景）的情况下改变角色所在地。"
        "如需切换场景，必须写明位移动作或明确时间跳跃标注。\n"
        "⚠️ 有感官基准的地点：正文中该地点的气味/光线/声音/温度描写，必须与「感官基准」保持一致，"
        "不得引入矛盾感官细节。"
    )
    return block


def _build_single_location_block(
    db: Session,
    project_id: str,
    location_id=None,
    location_name: str | None = None,
) -> str:
    """
    为单个 Scene 构建感官基准约束块，注入逐场起草 prompt。

    查找优先级：精确 location_id → 名称精确匹配 → 别名匹配 → 名称包含匹配。
    仅当命中 Location 且存在 sensory_signature 时才生成非空约束块；
    否则返回空字符串（不影响写章流程）。

    @param db:            SQLAlchemy Session
    @param project_id:    项目 UUID 字符串
    @param location_id:   Scene.location_id（UUID 或 None）
    @param location_name: Scene.location_name 文本兜底（location_id 未命中时使用）
    @returns 格式化约束文本块；无匹配数据时返回 ""
    """
    loc: Location | None = None

    if location_id:
        loc = db.query(Location).filter(Location.id == location_id).first()

    if not loc and location_name:
        all_locs = (
            db.query(Location)
            .filter(Location.project_id == project_id)
            .all()
        )
        loc_lower = location_name.strip().lower()
        for candidate in all_locs:
            if candidate.name.lower() == loc_lower:
                loc = candidate
                break
        if not loc:
            for candidate in all_locs:
                if any(a.lower() == loc_lower for a in (candidate.aliases or [])):
                    loc = candidate
                    break
        if not loc:
            for candidate in all_locs:
                if candidate.name.lower() in loc_lower or loc_lower in candidate.name.lower():
                    loc = candidate
                    break

    if not loc or not loc.sensory_signature:
        return ""

    danger_labels = {
        "safe": "安全", "neutral": "中性", "dangerous": "危险", "forbidden": "禁区",
    }
    lines = [
        f"【⚠️ 当前场景地点感官基准（必须遵守）】",
        f"地点：{loc.name}"
        + (f"（{danger_labels.get(loc.danger_level or 'neutral', loc.danger_level)}）"
           if loc.danger_level else ""),
        f"感官基准：{loc.sensory_signature.strip()}",
        "⚠️ 本场气味/光线/声音/温度描写必须与以上感官基准保持一致，不得引入矛盾感官细节。",
    ]
    if loc.controller:
        lines.append(f"控制方：{loc.controller}（影响角色在此地的行为自由度）")
    return "\n".join(lines)


def _plain_text_from_html(html: str) -> str:
    """HTML → 纯文本（去标签、保留换行语义）。"""
    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _save_chapter_content(db: Session, chapter: Chapter, plain_draft: str, attempt: int) -> None:
    """
    将本轮生成的纯文本稿保存到 Chapter，并创建 ChapterVersion 快照。

    @param db: SQLAlchemy Session
    @param chapter: Chapter ORM 对象（将被就地修改）
    @param plain_draft: 本轮生成的纯文本正文（不含索引块）
    @param attempt: 当前尝试次数（写入快照 note）
    """
    # 纯文本 → HTML（每段一 <p>）
    blocks = plain_draft.split("\n\n")
    html_content = "\n".join(
        f"<p>{b.strip().replace(chr(10), '<br>')}</p>"
        for b in blocks if b.strip()
    ) or "<p></p>"

    word_count = _count_words_plain(plain_draft)

    # 版本历史：整次门控只在第 1 轮起笔前备份一次（改写前原稿）。
    # 第 2/3 轮是内部质检迭代，不应各占一条用户可见的历史记录。
    if attempt == 1 and chapter_has_snapshot_worthy_content(chapter.content):
        snap = ChapterVersion(
            chapter_id=chapter.id,
            content=chapter.content,
            word_count=_count_words_plain(_plain_text_from_html(chapter.content)),
            note="质量门控重写前自动备份",
            is_auto=True,
        )
        db.add(snap)

    prev_plain_snapshot = (
        _plain_text_from_html(chapter.content).strip()
        if chapter_has_snapshot_worthy_content(chapter.content)
        else ""
    )

    chapter.content = html_content
    chapter.manuscript_raw_snapshot = prev_plain_snapshot or None
    chapter.word_count = word_count
    chapter.status = "writing"
    chapter.gated_draft_attempts = attempt
    db.commit()
    db.refresh(chapter)
