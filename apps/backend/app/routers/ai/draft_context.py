"""
draft_context.py — 起草路由的上下文组装 helpers

职责：提供 _build_draft_context 所依赖的小型辅助函数，避免单一路由文件膨胀。
这些函数均为 draft_routes.py 内部使用；需跨模块复用时请移入 services/ai/ 层。

禁止事项：
- 禁止在此模块新增 APIRouter 端点
- 禁止引入 DBSession 之外的副作用（写库操作属于路由层职责）
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models import (
    Character,
    ChapterAnalysisRecord,
    ChapterIndex,
    OutlineNode,
    ReaderPromise,
    Scene,
)
from app.routers.ai.text_utils import truncate

if TYPE_CHECKING:
    from app.models import Chapter


# ═══════════════════════════════════════════════════════════════
# 读者模拟反馈：上章分析结果注入写章路径
# ═══════════════════════════════════════════════════════════════

def _build_reader_feedback_context(
    db: Session,
    project_id: str,
    prev_chapter,
) -> str:
    """
    查询上一章最近一次 ChapterAnalysisRecord，将读者评分 / 劝退点 / 裁定 / 钩子建议
    格式化为可追加到 writing_brief_context 的文本块，让本章写作主动规避已知弱点。

    仅在上章存在分析记录时返回非空字符串；未分析过则静默跳过。

    @param db: SQLAlchemy Session
    @param project_id: 当前项目 UUID 字符串
    @param prev_chapter: 上一章 Chapter ORM 对象（可为 None）
    @returns 格式化后的读者反馈文本；无数据时返回空字符串
    """
    if prev_chapter is None:
        return ""
    try:
        record = (
            db.query(ChapterAnalysisRecord)
            .filter(
                ChapterAnalysisRecord.project_id == project_id,
                ChapterAnalysisRecord.chapter_id == prev_chapter.id,
            )
            .order_by(ChapterAnalysisRecord.created_at.desc())
            .first()
        )
    except Exception:
        return ""
    if record is None:
        return ""

    lines = ["\n【上章读者模拟反馈（本章写作必须回应）】"]
    risk_zh = {"low": "低", "medium": "中", "high": "⚠️高"}
    risk_label = risk_zh.get(record.drop_risk or "low", record.drop_risk or "")
    lines.append(f"  综合评分：{record.score}/10  流失风险：{risk_label}")
    if record.what_hooked:
        lines.append(f"  ✅ 读者买单：{record.what_hooked[:120]}")
    if record.what_repelled:
        lines.append(f"  ⚠️ 读者劝退：{record.what_repelled[:120]}（本章须主动规避）")
    if record.verdict:
        lines.append(f"  模拟裁定：{record.verdict[:160]}")
    if record.hook_suggestions:
        suggestions = [str(s) for s in (record.hook_suggestions or [])[:2] if s]
        if suggestions:
            lines.append("  本章钩子优化建议：" + "；".join(suggestions)[:180])
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 复盘闭环辅助：prev_directives 格式化
# ═══════════════════════════════════════════════════════════════

def _build_prev_directives(outline_node) -> str:
    """
    将 OutlineNode.extra.directives_from_prev 格式化为写章可用的纯文本指令块。

    debrief_routes 在复盘提交时将 next_chapter_directives 写入下一章
    OutlineNode.extra.directives_from_prev（最多保留最近5条）。
    本函数提取最近2条有效指令，组织成可注入 draft_assist_stream prev_directives 参数的字符串。

    @param outline_node: 当前章节对应的 OutlineNode ORM 对象（可为 None）
    @returns 格式化指令字符串；无有效指令时返回空字符串
    """
    if outline_node is None or not isinstance(outline_node.extra, dict):
        return ""
    dirs = outline_node.extra.get("directives_from_prev") or []
    if not dirs:
        return ""

    patch_key_zh = {
        "adjust_pacing": ("节奏调整", lambda v: v),
        "force_pov": ("强制POV视角", lambda v: v),
        "add_foreshadow": ("伏笔延续要求", lambda v: v),
        "reader_expectation_note": ("读者期待管理", lambda v: v),
        "must_resolve_promise_in_next_N_chapters": (
            "承诺兑现窗口",
            lambda v: f"本章或接下来 {v} 章内必须兑现已有读者承诺",
        ),
        "increase_screen_time_for": (
            "补足戏份",
            lambda v: "、".join(str(x) for x in (v or [])[:4]) + " 上章戏份不足，本章必须有实质场景",
        ),
    }

    dir_parts: list[str] = []
    for d in dirs[-2:]:
        patch = d.get("patch") or {}
        reason = (d.get("reason") or "").strip()
        from_title = (d.get("from_chapter_title") or "上章").strip()

        parts: list[str] = []
        for key, (label, fmt) in patch_key_zh.items():
            val = patch.get(key)
            if not val:
                continue
            try:
                parts.append(f"{label}：{fmt(val)}")
            except Exception:
                parts.append(f"{label}：{val}")

        if reason:
            parts.append(f"编辑理由：{reason}")
        if parts:
            dir_parts.append(f"[来自《{from_title}》复盘] " + "；".join(parts))

    return "\n".join(dir_parts)


# ═══════════════════════════════════════════════════════════════
# hook_strength 趋势预警辅助
# ═══════════════════════════════════════════════════════════════

def _append_hook_trend_warning(
    db: Session,
    project_id: str,
    current_sort_order: int,
    writing_brief_context: str,
    window: int = 5,
    threshold: float = 3.0,
) -> str:
    """
    查询本章之前最近 ``window`` 章的 hook_strength 均值，若低于 ``threshold``
    则向 writing_brief_context 追加主编强制钩子指令。

    @param db: SQLAlchemy Session
    @param project_id: 项目 UUID 字符串
    @param current_sort_order: 当前章节 sort_order
    @param writing_brief_context: 原文本（末尾追加）
    @param window: 向前回看的章节数，默认5
    @param threshold: 均值低于此值时触发预警，默认3.0（满分5）
    @returns 追加预警后的 writing_brief_context；未触发时原样返回
    """
    if current_sort_order <= 0:
        return writing_brief_context

    recent = (
        db.query(ChapterIndex.hook_strength)
        .filter(
            ChapterIndex.project_id == project_id,
            ChapterIndex.chapter_number < current_sort_order,
            ChapterIndex.hook_strength.isnot(None),
        )
        .order_by(ChapterIndex.chapter_number.desc())
        .limit(window)
        .all()
    )
    if len(recent) < 3:
        return writing_brief_context

    avg = sum(r[0] for r in recent) / len(recent)
    if avg >= threshold:
        return writing_brief_context

    warning = (
        f"\n\n▍【钩子趋势预警 · 主编强制指令】\n"
        f"近 {len(recent)} 章 hook_strength 均值 {avg:.1f}/5（连续偏弱），读者续读意愿存在系统性风险。\n"
        "本章章末钩子升级为最高优先级硬约束：\n"
        "· 必须选用悬念揭示型（A）或格局颠覆反转型（C）钩子，禁止以心理独白、景色描写或总结句收尾\n"
        "· 最后一段 ≤ 80 字，用一个具体的、尚未解决的行动/对话节点结束，不要解释、不要抒情\n"
        "· 该章整体须含 ≥ 1 处可被读者截图传播的「高光瞬间」以对冲前期低钩章带来的读者疲劳"
    )
    return writing_brief_context + warning


# ═══════════════════════════════════════════════════════════════
# ReaderPromise 写章注入辅助
# ═══════════════════════════════════════════════════════════════

def _build_reader_promise_context(
    db: Session,
    project_id: str,
    chapter_sort_order: int,
    lookahead: int = 5,
) -> str:
    """
    查询当前章节覆盖窗口内 open 状态的读者承诺，格式化为写章约束文本。

    分两级：
    - 必须兑现：承诺截止章号 ≤ 当前 sort_order（已到期）
    - 可以兑现：截止章号在 [当前+1, 当前+lookahead] 内，或 priority≥4 的无截止高优承诺

    @returns 格式化文本；无匹配承诺时返回空字符串。
    """
    open_promises: list[ReaderPromise] = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .order_by(ReaderPromise.priority.desc())
        .limit(40)
        .all()
    )
    if not open_promises:
        return ""

    must_fulfill: list[ReaderPromise] = []
    can_fulfill: list[ReaderPromise] = []

    for p in open_promises:
        if p.expected_chapter_window is not None:
            src = p.source_chapter_number or 0
            deadline = src + p.expected_chapter_window
        else:
            deadline = None

        if deadline is not None and deadline <= chapter_sort_order:
            must_fulfill.append(p)
        elif deadline is not None and chapter_sort_order < deadline <= chapter_sort_order + lookahead:
            can_fulfill.append(p)
        elif deadline is None and (p.priority or 3) >= 4:
            can_fulfill.append(p)

    if not must_fulfill and not can_fulfill:
        return ""

    type_zh = {
        "chapter_ending": "章末预告",
        "volume_ending": "卷末预告",
        "name_implication": "名字/称号暗示",
        "chapter_comment_consensus": "章评共识",
        "protagonist_claim": "主角宣言",
    }

    def _fmt(p: ReaderPromise, show_deadline: bool = False) -> str:
        ptype = type_zh.get(p.promise_type or "", p.promise_type or "承诺")
        stars = "⭐" * min(max(p.priority or 3, 1), 5)
        line = f"  [{ptype} {stars}] {p.promise_text}"
        if show_deadline and p.expected_chapter_window is not None:
            src = p.source_chapter_number or 0
            line += f"  （截止第 {src + p.expected_chapter_window} 章）"
        return line

    lines: list[str] = ["【读者承诺台账（写章时必须对照）】"]
    if must_fulfill:
        lines.append(f"⚠️  本章【必须兑现】的承诺（共 {len(must_fulfill)} 条，已到期）：")
        for p in must_fulfill:
            lines.append(_fmt(p, show_deadline=True))
    if can_fulfill:
        lines.append(f"💡  本章【可以兑现】的承诺（共 {len(can_fulfill)} 条，即将到期或高优先级）：")
        for p in can_fulfill:
            lines.append(_fmt(p, show_deadline=True))
    lines.append(
        "兑现要求：在正文中以具体行动/对话/事件落实承诺，不要口号式敷衍；"
        "复盘环节会自动检测兑现情况并更新承诺状态，不需要在正文里追加任何标注。"
    )
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Scene 蓝图格式化辅助
# ═══════════════════════════════════════════════════════════════

def _build_scene_blueprint(
    db: Session,
    project_id: str,
    chapter: "Chapter",
    outline_node: "OutlineNode | None",
) -> str:
    """
    查询本章对应的 Scene 记录，格式化为结构化分场蓝图文本。

    查找顺序：
    1. 按 outline_node_id 匹配（Bootstrap 生成的场景）
    2. 按 chapter_id 匹配（已成稿绑定的场景）

    @returns 格式化后的分场蓝图字符串；无 Scene 记录时返回空字符串。
    """
    scenes: list[Scene] = []

    if outline_node is not None:
        scenes = (
            db.query(Scene)
            .filter(
                Scene.project_id == project_id,
                Scene.outline_node_id == outline_node.id,
            )
            .order_by(Scene.order)
            .all()
        )

    if not scenes and chapter.id is not None:
        scenes = (
            db.query(Scene)
            .filter(
                Scene.project_id == project_id,
                Scene.chapter_id == chapter.id,
            )
            .order_by(Scene.order)
            .all()
        )

    if not scenes:
        return ""

    char_ids: set = set()
    for sc in scenes:
        if sc.pov_character_id:
            char_ids.add(str(sc.pov_character_id))
        for cid in (sc.characters_on_stage or []):
            char_ids.add(str(cid))

    id_to_name: dict[str, str] = {}
    if char_ids:
        rows = (
            db.query(Character.id, Character.name)
            .filter(Character.id.in_(char_ids))
            .all()
        )
        id_to_name = {str(r.id): r.name for r in rows}

    total_budget = sum(sc.word_budget or 0 for sc in scenes)
    lines: list[str] = [
        f"【本章分场蓝图（共 {len(scenes)} 场，总预算约 {total_budget} 字）】",
        "严格按此结构逐场写作，每场字数在预算 ±15% 内；每场以钩子收束，串联下一场。",
        "",
    ]

    pacing_zh = {"fast": "快节奏", "mid": "中节奏", "slow": "慢节奏"}

    for sc in scenes:
        pov_name = id_to_name.get(str(sc.pov_character_id), "") if sc.pov_character_id else ""
        on_stage = [id_to_name.get(str(cid), str(cid)) for cid in (sc.characters_on_stage or [])]
        on_stage_str = "、".join(n for n in on_stage if n) or ""
        pacing_str = pacing_zh.get(sc.pacing or "mid", sc.pacing or "mid")
        hook_stars = "⭐" * min(max(sc.hook_strength or 3, 1), 5)
        budget = sc.word_budget or 400

        scene_lines = [
            f"▶ 场 {sc.order}｜{sc.title or '（无标题）'}  （预算 {budget} 字，{pacing_str}）",
        ]
        if sc.location_name:
            scene_lines.append(f"  地点：{sc.location_name}")
        if sc.time:
            scene_lines.append(f"  时间：{sc.time}")
        if pov_name:
            scene_lines.append(f"  POV：{pov_name}")
        if on_stage_str:
            scene_lines.append(f"  在场：{on_stage_str}")
        if sc.goal:
            scene_lines.append(f"  目标：{sc.goal}")
        if sc.conflict:
            scene_lines.append(f"  冲突：{sc.conflict}")
        if sc.turn:
            scene_lines.append(f"  转折：{sc.turn}")
        if sc.hook:
            scene_lines.append(f"  钩子：{sc.hook}（强度 {hook_stars}）")
        if sc.sensory_focus and sc.sensory_focus != "mixed":
            sense_zh = {
                "sight": "视觉", "sound": "听觉", "smell": "嗅觉",
                "taste": "味觉", "touch": "触觉",
            }
            scene_lines.append(f"  感官焦点：{sense_zh.get(sc.sensory_focus, sc.sensory_focus)}")

        lines.extend(scene_lines)
        lines.append("")

    return "\n".join(lines).rstrip()


# ═══════════════════════════════════════════════════════════════
# 人物清单与摘要构建（从 _build_draft_context 抽出，减少单函数行数）
# ═══════════════════════════════════════════════════════════════

def _build_character_summary(
    db: Session,
    project_id: str,
    characters: list,
    outline_node,
    chapter,
    large_context: bool,
) -> tuple[str, list[str]]:
    """
    构建章节人物摘要字符串与本章人物清单（manifest）。

    从 characters 列表中筛选本章出场人物，按 large_context 模式组装详细或简短摘要。
    同时构建 chapter_manifest_names 作为 AI 的出场限制约束。

    @param db: SQLAlchemy Session
    @param project_id: 项目 UUID 字符串
    @param characters: 当前项目所有 Character 记录
    @param outline_node: 章节大纲节点（可为 None）
    @param chapter: 当前 Chapter ORM 对象
    @param large_context: 是否使用大上下文模式
    @returns (char_summary, chapter_manifest_names) 元组
    """
    involved_ids: set = set()
    if outline_node and outline_node.involved_character_ids:
        involved_ids = set(str(cid) for cid in (outline_node.involved_character_ids or []))

    def _char_skill_names(known_skills) -> str:
        if not known_skills:
            return ""
        skill_limit = 10 if large_context else 3
        names = [
            sk.get("skill_name", "") if isinstance(sk, dict) else str(sk)
            for sk in known_skills[:skill_limit]
        ]
        return "、".join(n for n in names if n)

    chapter_manifest_names: list[str] = []
    if involved_ids:
        priority = [c for c in characters if str(c.id) in involved_ids]
        display_chars = priority
        chapter_manifest_names = [c.name for c in priority]
    else:
        display_chars = characters if large_context else characters[:6]

    # manifest 兜底：从核心角色 + 最近 5 章首次出场凑一份
    if not chapter_manifest_names:
        seen: set[str] = set()
        fallback_names: list[str] = []

        for c in characters:
            if not c.name:
                continue
            is_core = c.role in ("protagonist", "antagonist") or (c.character_tier == "core")
            if is_core and c.name not in seen:
                fallback_names.append(c.name)
                seen.add(c.name)

        if chapter.sort_order is not None and chapter.sort_order > 1:
            recent_indexes = (
                db.query(ChapterIndex)
                .filter(
                    ChapterIndex.project_id == project_id,
                    ChapterIndex.chapter_number < chapter.sort_order,
                    ChapterIndex.chapter_number >= max(1, chapter.sort_order - 5),
                )
                .order_by(ChapterIndex.chapter_number.desc())
                .all()
            )
            for ci in recent_indexes:
                for fa in (ci.first_appearances or [])[:8]:
                    name = (fa.get("name") if isinstance(fa, dict) else "") or ""
                    name = name.strip()
                    if name and name not in seen:
                        fallback_names.append(name)
                        seen.add(name)
                if len(fallback_names) >= 12:
                    break

        chapter_manifest_names = fallback_names[:12]

    char_lines = []
    for c in display_chars:
        parts = [f"{c.name}（{c.role}"]
        if large_context and c.alias:
            parts.append(f"别名:{c.alias}")
        if c.current_realm:
            parts.append(f"境界:{c.current_realm}")
        if large_context and c.realm_rank is not None:
            parts.append(f"境界序号:{c.realm_rank}")
        if c.current_location:
            parts.append(f"位置:{c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态:{c.current_status}")
        skills_str = _char_skill_names(c.known_skills)
        if skills_str:
            parts.append(f"技能:[{skills_str}]")
        parts.append(f"）性格:{(c.personality or '')[:40]}")
        if c.motivation:
            parts.append(f"动机:{truncate(c.motivation, 180 if large_context else 30)}")
        if large_context and c.values:
            parts.append(f"价值观:{truncate(c.values, 180)}")
        if large_context and c.fear:
            parts.append(f"恐惧:{truncate(c.fear, 140)}")
        if large_context and c.secrets:
            parts.append(f"秘密:{truncate(c.secrets, 180)}")
        if large_context and c.known_skills:
            parts.append(f"技能明细:{json.dumps(c.known_skills, ensure_ascii=False)[:1200]}")
        if large_context and c.owned_items:
            parts.append(f"持有物:{json.dumps(c.owned_items, ensure_ascii=False)[:1200]}")

        _speech_kit = (c.speech_kit or {}) if isinstance(c.speech_kit, dict) else {}
        if large_context and _speech_kit:
            _sig_words = [str(w) for w in (_speech_kit.get("signature_words") or []) if w][:5]
            if _sig_words:
                parts.append(f"标志词:[{'、'.join(_sig_words)}]")
            _samples = [str(s) for s in (_speech_kit.get("sample_dialogues") or []) if s][-3:]
            if _samples:
                parts.append("样本台词:「" + "」｜「".join(_samples) + "」")
            _evo_notes = _speech_kit.get("recent_evolution_notes") or []
            if _evo_notes:
                _latest_evo = str(_evo_notes[-1])[:80]
                if _latest_evo:
                    parts.append(f"近期声音演变:{_latest_evo}")
        elif not large_context and c.speech_style:
            parts.append(f"口吻:{c.speech_style[:30]}")

        if large_context:
            _arc_stages = c.arc_stages if isinstance(c.arc_stages, list) else []
            _cur_stage = next(
                (s for s in _arc_stages if isinstance(s, dict) and not s.get("completed")),
                _arc_stages[-1] if _arc_stages else None,
            )
            if _cur_stage and isinstance(_cur_stage, dict):
                _stage_name = (_cur_stage.get("name") or _cur_stage.get("stage") or "").strip()
                _stage_goal = (_cur_stage.get("goal") or _cur_stage.get("description") or "").strip()
                if _stage_name:
                    parts.append(
                        f"成长弧:[{_stage_name}]{f'({_stage_goal[:50]})' if _stage_goal else ''}"
                    )
        char_lines.append("".join(parts))

    char_summary = "\n".join(char_lines) if large_context else " | ".join(char_lines)
    return char_summary, chapter_manifest_names
