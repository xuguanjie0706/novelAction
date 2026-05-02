from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Any, Awaitable, Callable, List, Literal, Optional
from uuid import UUID
import json
import re

from app.database import SessionLocal, get_db
from app.models import (
    Character,
    Faction,
    Foreshadow,
    Item,
    OutlineNode,
    OutlineRevision,
    PowerSystem,
    Project,
    Skill,
    StoryLine,
    WorldSetting,
)
from app.models.chapter import Chapter
from app.schemas import OutlineNodeCreate, OutlineNodeUpdate, OutlineNodeOut
from app.services.ai_service import AIService
from app.services.outline_planning import (
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    normalize_volume_plan,
)
from app.services.workflow_graph import WorkflowGraph, WorkflowNode, workflow_runs
from app.utils.chapter_numbering import display_chapter_number

router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])


def build_tree(nodes: List[OutlineNode]) -> List[OutlineNodeOut]:
    """把扁平列表组装成嵌套树（所有层级均按 sort_order 排序）"""
    node_map = {str(n.id): OutlineNodeOut.model_validate(n) for n in nodes}
    # model_validate(from_attributes) 会带入 SQLAlchemy 已加载的 children；
    # 若再按 parent_id 挂接，同一子节点会出现两次（卷下两篇、章重复等）。
    for node_out in node_map.values():
        node_out.children.clear()
    roots = []
    for node_out in node_map.values():
        if node_out.parent_id is None:
            roots.append(node_out)
        else:
            parent = node_map.get(str(node_out.parent_id))
            if parent:
                parent.children.append(node_out)

    def sort_recursive(node_list: list) -> None:
        node_list.sort(key=lambda x: x.sort_order)
        for n in node_list:
            if n.children:
                sort_recursive(n.children)

    sort_recursive(roots)
    return roots


def _clean_outline_text(value: object, limit: int = 120) -> str:
    return " ".join(str(value or "").split())[:limit]


def _is_xuanhuan_like_genre(genre: str | None) -> bool:
    raw = (genre or "").strip()
    return any(tag in raw for tag in ("玄幻", "仙侠", "古风", "武侠"))


def _sanitize_xuanhuan_outline_text(text: str) -> str:
    cleaned = text
    replacements = [
        ("首席工程师", "大阵主祭"),
        ("AI化", "傀儡化"),
        ("人工智能", "灵智禁制"),
        ("AI", "灵智"),
        ("半机械", "半傀"),
        ("机械", "机关"),
        ("芯片", "命纹碎片"),
        ("量子", "微尘"),
        ("基因实验室", "血脉禁室"),
        ("星际文明", "诸天古域"),
        ("星际", "诸天"),
        ("程序上传", "神识刻印"),
        ("控制台", "阵枢石台"),
    ]
    for src, dst in replacements:
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _sanitize_generated_outline_chapter(chapter: dict, genre: str | None) -> dict:
    if not _is_xuanhuan_like_genre(genre):
        return chapter
    sanitized = dict(chapter)
    for field in ("title", "opening_hook", "core_event", "character_change", "foreshadow", "end_hook"):
        value = sanitized.get(field)
        if isinstance(value, str) and value:
            sanitized[field] = _sanitize_xuanhuan_outline_text(value)
    return sanitized


def _outline_batch_size(model_profile: str) -> int:
    return 30 if model_profile == "gemini" else 15


def _format_previous_chapters_context(chapters: list[dict], max_items: int = 10) -> str:
    if not chapters:
        return ""

    lines = []
    for chapter in chapters[-max_items:]:
        number = chapter.get("number") or "?"
        title = _clean_outline_text(chapter.get("title"), 40) or "未命名"
        core_event = _clean_outline_text(chapter.get("core_event"), 120)
        character_change = _clean_outline_text(chapter.get("character_change"), 100)
        foreshadow = _clean_outline_text(chapter.get("foreshadow"), 100)
        end_hook = _clean_outline_text(chapter.get("end_hook"), 120)
        lines.append(
            f"第{number}章：{title} | 核心事件：{core_event} | 人物变化：{character_change} | "
            f"伏笔：{foreshadow} | 章末钩子：{end_hook}"
        )
    return "\n".join(lines)


def _format_rolling_continuity_state(chapters: list[dict]) -> str:
    if not chapters:
        return ""

    last = chapters[-1]
    last_number = last.get("number") or "?"
    last_title = _clean_outline_text(last.get("title"), 40) or "未命名"
    last_hook = _clean_outline_text(last.get("end_hook"), 160) or "（上一批未给出章末钩子）"

    recent_foreshadows = [
        _clean_outline_text(chapter.get("foreshadow"), 120)
        for chapter in chapters[-8:]
        if _clean_outline_text(chapter.get("foreshadow"), 120)
    ]
    recent_events = [
        _clean_outline_text(chapter.get("core_event"), 120)
        for chapter in chapters[-6:]
        if _clean_outline_text(chapter.get("core_event"), 120)
    ]

    lines = [
        f"上一批最后章节：第{last_number}章《{last_title}》",
        f"下一批开篇必须承接：{last_hook}",
    ]
    if recent_foreshadows:
        lines.append(f"未回收/待处理伏笔：{'；'.join(recent_foreshadows)}")
    if recent_events:
        lines.append(f"不得重复已发生的核心事件：{'；'.join(recent_events)}")
    return "\n".join(lines)


def _format_book_quality_continuity_state(chapters: list[dict]) -> str:
    """
    Book-level outline QA receives all target chapter plans as the object under review.
    It must not recycle those same plans into the "already happened" rolling ledger.
    """
    chapter_count = len(chapters)
    return (
        f"全书质检不使用滚动连续性账本：当前 {chapter_count} 个章节计划全部属于待检对象，"
        "不得把待检章节自身当作已发生事实来判定重复。"
    )


def _format_outline_batch_goal(
    node_title: str,
    batch_offset: int,
    batch_count: int,
    planned_chapters: int,
    node_generated_chapters: int | None = None,
) -> str:
    global_start = batch_offset + 1
    global_end = batch_offset + batch_count
    local_done = batch_offset if node_generated_chapters is None else node_generated_chapters
    local_start = local_done + 1
    local_end = local_done + batch_count
    return (
        f"本批生成全书第{global_start}-{global_end}章，也是《{node_title}》本卷第{local_start}-{local_end}章；"
        f"《{node_title}》共{planned_chapters}章。本批要承接已有章节，不得重启本卷冲突或提前透支后续卷爆点。"
    )


def _format_outline_word_budget_context(
    *,
    target_words: int | None,
    chapter_count: int,
    chapter_word_target: int = TARGET_WORDS_PER_CHAPTER,
    scope_label: str = "全书",
) -> str:
    estimated_words = max(0, chapter_count) * chapter_word_target
    lines = [
        f"{scope_label}当前章节数：{chapter_count} 章",
        f"{scope_label}按每章约{chapter_word_target}字估算：约{estimated_words}字",
    ]
    if target_words and target_words > 0:
        gap = target_words - estimated_words
        gap_label = f"+{gap}" if gap >= 0 else str(gap)
        lines.append(f"{scope_label}目标总字数：{target_words}字（差值：{gap_label}字）")
    else:
        lines.append(f"{scope_label}目标总字数：未设置（建议在项目中设定 target_words）")
    lines.append(
        f"{scope_label}节奏要求：禁止后期跨位面速刷；必须保证中后期仍有足够章节承载势力升级、人物代价、伏笔回收与终局铺垫。"
    )
    return "\n".join(lines)


def _format_global_outline_context(volume_nodes: list[tuple[OutlineNode, int]]) -> str:
    lines = []
    for idx, (node, planned_chapters) in enumerate(volume_nodes, start=1):
        extra = node.extra if isinstance(node.extra, dict) else {}
        lines.append(
            f"{idx}. 《{node.title}》{planned_chapters}章 | "
            f"摘要：{_clean_outline_text(node.summary, 120)} | "
            f"阶段立意：{_clean_outline_text(extra.get('theme_stage'), 120)} | "
            f"人物弧：{_clean_outline_text(extra.get('character_arc'), 120)} | "
            f"核心悬念：{_clean_outline_text(node.hook, 100)} | "
            f"主要冲突：{_clean_outline_text(node.conflict, 100)}"
        )
    return "\n".join(lines)


def _format_json_list(value: object, max_items: int = 3) -> str:
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            chapter_range = _clean_outline_text(item.get("chapter_range"), 24)
            stage = _clean_outline_text(item.get("stage") or item.get("name"), 40)
            state = _clean_outline_text(item.get("state"), 60)
            label = ":".join(part for part in [chapter_range, stage] if part)
            if state:
                label = f"{label}({state})" if label else state
            if label:
                parts.append(label)
        else:
            text = _clean_outline_text(item, 60)
            if text:
                parts.append(text)
    return "、".join(parts)


def _format_outline_quality_story_bible(
    *,
    project: Project,
    settings: list[WorldSetting],
    characters: list[Character],
    storylines: list[StoryLine],
    power_systems: list[PowerSystem],
    factions: list[Faction],
    items: list[Item],
    foreshadows: list[Foreshadow],
    skills: list[Skill] | None = None,
) -> str:
    """
    Build a compact fact ledger for outline QA.
    It is intentionally structured as constraints, not prose, so the model can
    catch deaths, item symbolism, world rules, and arc regressions.
    """
    sections: list[str] = []
    story_core = project.story_core if isinstance(project.story_core, dict) else {}

    core_lines = []
    if project.premise:
        core_lines.append(f"立意/边界：{_clean_outline_text(project.premise, 240)}")
    if project.world_overview:
        core_lines.append(f"世界概览：{_clean_outline_text(project.world_overview, 220)}")
    if story_core.get("theme"):
        core_lines.append(f"主题命题：{_clean_outline_text(story_core.get('theme'), 180)}")
    if core_lines:
        sections.append("【作品核心约束】\n" + "\n".join(f"- {line}" for line in core_lines))

    if settings:
        lines = []
        for setting in settings[:12]:
            tags = _format_json_list(setting.tags, max_items=4)
            tag_text = f" [{tags}]" if tags else ""
            lines.append(
                f"- {setting.title}{tag_text}：{_clean_outline_text(setting.content, 220)}"
            )
        sections.append("【世界观/规则卡】\n" + "\n".join(lines))

    if characters:
        lines = []
        for character in characters[:16]:
            stages = _format_json_list(character.arc_stages, max_items=4)
            parts = [
                f"{character.name}（{character.role or 'unknown'}）状态={character.current_status or 'unknown'}",
            ]
            if character.current_realm:
                parts.append(f"境界={_clean_outline_text(character.current_realm, 40)}")
            if character.faction:
                parts.append(f"阵营={_clean_outline_text(character.faction, 40)}")
            if character.arc:
                parts.append(f"弧线={_clean_outline_text(character.arc, 180)}")
            if stages:
                parts.append(f"阶段={stages}")
            lines.append("- " + " | ".join(parts))
        sections.append("【人物状态与弧线】\n" + "\n".join(lines))

    if storylines:
        lines = []
        for storyline in storylines[:12]:
            beats = _format_json_list(storyline.key_beats, max_items=3)
            parts = [
                f"{storyline.name}（{storyline.line_type or 'unknown'}/{storyline.status or 'unknown'}）",
            ]
            if storyline.core_conflict:
                parts.append(f"冲突={_clean_outline_text(storyline.core_conflict, 140)}")
            if storyline.resolution_direction:
                parts.append(f"解决方向={_clean_outline_text(storyline.resolution_direction, 140)}")
            if beats:
                parts.append(f"节拍={beats}")
            lines.append("- " + " | ".join(parts))
        sections.append("【故事线进度】\n" + "\n".join(lines))

    if power_systems:
        lines = []
        for system in power_systems[:6]:
            levels = _format_json_list(system.levels, max_items=5)
            parts = [system.name]
            if system.description:
                parts.append(f"定位={_clean_outline_text(system.description, 140)}")
            if system.breakthrough_condition:
                parts.append(f"突破={_clean_outline_text(system.breakthrough_condition, 120)}")
            if levels:
                parts.append(f"境界={levels}")
            lines.append("- " + " | ".join(parts))
        sections.append("【力量体系】\n" + "\n".join(lines))

    if factions:
        lines = []
        for faction in factions[:10]:
            parts = [f"{faction.name}（{faction.alignment or 'unknown'}）"]
            if faction.strength_level:
                parts.append(f"实力={_clean_outline_text(faction.strength_level, 80)}")
            if faction.goals:
                parts.append(f"目标={_clean_outline_text(faction.goals, 140)}")
            if faction.secrets:
                parts.append(f"秘密={_clean_outline_text(faction.secrets, 120)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【势力格局】\n" + "\n".join(lines))

    if items:
        lines = []
        for item in items[:12]:
            parts = [f"{item.name}（{item.rarity or 'unknown'}/{item.status or 'unknown'}）"]
            if item.story_significance:
                parts.append(f"意义={_clean_outline_text(item.story_significance, 160)}")
            if item.effects:
                parts.append(f"效果={_clean_outline_text(item.effects, 100)}")
            if item.limitations:
                parts.append(f"限制={_clean_outline_text(item.limitations, 100)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【核心道具】\n" + "\n".join(lines))

    if skills:
        lines = []
        for skill in skills[:10]:
            parts = [f"{skill.name}（{skill.skill_type or 'unknown'}/{skill.grade or 'unknown'}）"]
            if skill.effects:
                parts.append(f"效果={_clean_outline_text(skill.effects, 100)}")
            if skill.limitations:
                parts.append(f"限制={_clean_outline_text(skill.limitations, 100)}")
            lines.append("- " + " | ".join(parts))
        sections.append("【关键技能】\n" + "\n".join(lines))

    if foreshadows:
        lines = []
        for foreshadow in foreshadows[:16]:
            code = foreshadow.code or "未编号"
            parts = [
                f"{code}：{foreshadow.title}（{foreshadow.status or 'unknown'}，优先级{foreshadow.priority or '-'}）",
            ]
            if foreshadow.planned_resolve_chapter:
                parts.append(f"预计第{foreshadow.planned_resolve_chapter}章处理")
            if foreshadow.description:
                parts.append(_clean_outline_text(foreshadow.description, 160))
            lines.append("- " + " | ".join(parts))
        sections.append("【伏笔台账】\n" + "\n".join(lines))

    return "\n\n".join(sections)


def _chapter_duplicate_signature(chapter: dict) -> tuple[str, str, str] | None:
    core_event = _clean_outline_text(chapter.get("core_event"), 240)
    character_change = _clean_outline_text(chapter.get("character_change"), 220)
    end_hook = _clean_outline_text(chapter.get("end_hook"), 220)
    if not core_event or not (character_change or end_hook):
        return None
    return (core_event, character_change, end_hook)


def _detect_outline_hard_rule_issues(chapters: list[dict]) -> dict:
    """
    Deterministic outline checks for failures that should not depend on LLM judgment.
    Keep this narrow: exact mirrored chapter endings are always structural defects.
    """
    signatures: dict[tuple[str, str, str], list[int]] = {}
    for chapter in chapters:
        signature = _chapter_duplicate_signature(chapter)
        number = chapter.get("number")
        if signature is None or not isinstance(number, int):
            continue
        signatures = {
            **signatures,
            signature: [*signatures.get(signature, []), number],
        }

    issues = []
    must_fix: set[int] = set()
    for numbers in signatures.values():
        if len(numbers) < 2:
            continue
        ordered_numbers = sorted(numbers)
        must_fix = {*must_fix, *ordered_numbers}
        issues.append({
            "severity": "critical",
            "type": "duplicate_event",
            "chapter_numbers": ordered_numbers,
            "description": (
                f"第{'、'.join(str(n) for n in ordered_numbers)}章的核心事件、人物变化、章末钩子完全一致，"
                "属于确定性镜像重复，会制造多个同质结局或循环节点。"
            ),
            "suggested_patch": {
                "chapter_number": ordered_numbers[-1],
                "field": "core_event",
                "replacement": "",
            },
        })

    if not issues:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "硬规则未发现确定性结构问题。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }

    return {
        "overall_score": 55,
        "status": "fail",
        "summary": f"硬规则发现 {len(issues)} 个确定性结构问题。",
        "issues": issues,
        "must_fix_chapter_numbers": sorted(must_fix),
    }


def _merge_outline_quality_reports(ai_report: dict, hard_report: dict) -> dict:
    hard_issues = hard_report.get("issues") if isinstance(hard_report, dict) else []
    if not hard_issues:
        return ai_report

    ai_issues = ai_report.get("issues") if isinstance(ai_report, dict) else []
    ai_must_fix = ai_report.get("must_fix_chapter_numbers") if isinstance(ai_report, dict) else []
    hard_must_fix = hard_report.get("must_fix_chapter_numbers") or []
    merged_must_fix = sorted({
        *[n for n in ai_must_fix if isinstance(n, int)],
        *[n for n in hard_must_fix if isinstance(n, int)],
    })

    ai_score = ai_report.get("overall_score") if isinstance(ai_report, dict) else None
    hard_score = hard_report.get("overall_score", 55)
    score = min(ai_score if isinstance(ai_score, int) else 100, hard_score)
    ai_summary = ai_report.get("summary", "") if isinstance(ai_report, dict) else ""
    hard_summary = hard_report.get("summary", "")
    summary = "；".join(part for part in [hard_summary, ai_summary] if part)

    return {
        **(ai_report if isinstance(ai_report, dict) else {}),
        "overall_score": score,
        "status": "fail",
        "summary": summary,
        "issues": [*hard_issues, *(ai_issues if isinstance(ai_issues, list) else [])],
        "must_fix_chapter_numbers": merged_must_fix,
    }


def _format_outline_quality_label(node_title: str, report: dict, scope: str) -> str:
    scope_name = "全书" if scope == "book" else "卷内"
    if not isinstance(report, dict) or report.get("error"):
        return f"《{node_title}》{scope_name}质检失败：{report.get('error', '未知错误') if isinstance(report, dict) else '未知错误'}"
    score = report.get("overall_score", "-")
    status = report.get("status", "-")
    must_fix = report.get("must_fix_chapter_numbers") or []
    suffix = f"，必修章节：{'、'.join(str(num) for num in must_fix)}" if must_fix else ""
    return f"《{node_title}》{scope_name}质检完成：{score}分 / {status}{suffix}"


def _sse_outline_quality_progress(
    *,
    step: int,
    total_steps: int,
    label: str,
    scope: str,
    progress_key_suffix: str,
    report: dict | None = None,
    done: bool = True,
    error: bool = False,
) -> str:
    """SSE 进度行：携带结构化大纲质检结果供前端展开；progress_key 避免与同日 step 的其他进度行合并。"""
    payload: dict = {
        "event": "progress",
        "step": step,
        "total": total_steps,
        "label": label,
        "done": done,
        "error": error,
        "progress_key": f"{step}-outline-quality-{scope}-{progress_key_suffix}",
        "outline_quality_scope": scope,
    }
    if report is not None:
        payload["outline_quality_report"] = report
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _outline_node_to_chapter_context(node: OutlineNode) -> dict:
    title_text = str(node.title or "")
    match = re.match(r"第(\d+)章[:：]\s*(.*)", title_text)
    number = display_chapter_number(title_text, getattr(node, "sort_order", None))
    title = match.group(2).strip() if match else title_text
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "number": number,
        "title": title or "未命名",
        "core_event": node.summary or "",
        "opening_hook": node.hook or "",
        "character_change": node.conflict or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
        "pacing": extra.get("pacing", "medium"),
        "word_estimate": extra.get("word_estimate", TARGET_WORDS_PER_CHAPTER),
    }


def _load_existing_chapter_context(
    db: Session,
    project_id: str,
    limit: int = 24,
) -> list[dict]:
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters[-limit:]


def _outline_snapshot_payload(nodes: list[OutlineNode]) -> dict:
    ordered = sorted(
        nodes,
        key=lambda node: (
            0 if node.parent_id is None else 1,
            node.sort_order or 0,
            str(node.id),
        ),
    )
    return {
        "schema_version": 1,
        "nodes": [
            {
                "id": str(node.id),
                "parent_id": str(node.parent_id) if node.parent_id else None,
                "node_type": node.node_type,
                "title": node.title,
                "summary": node.summary,
                "hook": node.hook,
                "highlight": node.highlight,
                "conflict": node.conflict,
                "sort_order": node.sort_order,
                "expected_words": node.expected_words,
                "reader_hook_score": node.reader_hook_score,
                "storyline_ids": node.storyline_ids or [],
                "involved_character_ids": node.involved_character_ids or [],
                "key_item_ids": node.key_item_ids or [],
                "key_skill_ids": node.key_skill_ids or [],
                "emotional_tone": node.emotional_tone,
                "pacing": node.pacing,
                "power_milestone": node.power_milestone,
                "foreshadows_laid": node.foreshadows_laid or [],
                "foreshadows_resolved": node.foreshadows_resolved or [],
                "extra": node.extra if isinstance(node.extra, dict) else {},
            }
            for node in ordered
        ],
    }


def _create_outline_revision(
    db: Session,
    *,
    project_id: str,
    label: str,
    source: str,
    scope: str = "book",
    volume_node_id: UUID | None = None,
    note: str | None = None,
    meta: dict[str, Any] | None = None,
) -> OutlineRevision:
    q = db.query(OutlineNode).filter(OutlineNode.project_id == project_id)
    if scope == "volume" and volume_node_id:
        direct_children = db.query(OutlineNode.id).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id == volume_node_id,
        ).all()
        child_ids = [row[0] for row in direct_children]
        q = q.filter(
            (OutlineNode.id == volume_node_id)
            | (OutlineNode.parent_id == volume_node_id)
            | (OutlineNode.parent_id.in_(child_ids))
        )
    nodes = q.order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    snapshot = _outline_snapshot_payload(nodes)
    revision = OutlineRevision(
        project_id=project_id,
        label=label,
        source=source,
        scope=scope,
        volume_node_id=volume_node_id,
        note=note,
        snapshot=snapshot,
        meta=meta or {},
        node_count=len(snapshot["nodes"]),
    )
    db.add(revision)
    db.commit()
    db.refresh(revision)
    return revision


def _load_volume_chapter_context(
    db: Session,
    project_id: str,
    volume_node: OutlineNode,
) -> list[dict]:
    """
    Load chapter plans under a volume, including the legacy volume -> arc -> chapter_plan shape.
    """
    children = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id == volume_node.id,
    ).all()
    parent_ids = [volume_node.id, *[child.id for child in children if child.node_type == "arc"]]
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
        OutlineNode.parent_id.in_(parent_ids),
    ).all()
    chapters = [_outline_node_to_chapter_context(node) for node in nodes]
    chapters.sort(key=lambda chapter: chapter.get("number") or 0)
    return chapters


def _chapter_number_value(chapter: dict) -> int:
    number = chapter.get("number")
    return number if isinstance(number, int) else 0


def _with_outline_quality(report_owner: OutlineNode, report: dict) -> dict:
    current_extra = report_owner.extra if isinstance(report_owner.extra, dict) else {}
    return {
        **current_extra,
        "outline_quality": report,
    }


def _create_quality_revision(
    db: Session,
    *,
    project_id: str,
    scope: str,
    report: dict[str, Any],
    volume_node: OutlineNode | None = None,
) -> OutlineRevision:
    if scope == "volume" and volume_node is not None:
        label = f"质检报告：{volume_node.title}"
        note = "单卷大纲质检自动留档"
        volume_node_id = volume_node.id
    else:
        label = "质检报告：全书大纲"
        note = "全书大纲质检自动留档"
        volume_node_id = None
    return _create_outline_revision(
        db,
        project_id=project_id,
        label=label,
        source="quality",
        scope="volume" if scope == "volume" else "book",
        volume_node_id=volume_node_id,
        note=note,
        meta={
            "quality_scope": scope,
            "quality_status": report.get("status"),
            "quality_score": report.get("overall_score"),
            "quality_report": report,
        },
    )


def _outline_node_plan_fields(node: OutlineNode) -> dict:
    extra = node.extra if isinstance(node.extra, dict) else {}
    return {
        "opening_hook": node.hook or "",
        "core_event": node.summary or "",
        "character_change": node.conflict or "",
        "foreshadow": extra.get("foreshadow", ""),
        "end_hook": extra.get("end_hook") or node.highlight or "",
    }


def _apply_outline_patch_to_node(node: OutlineNode, patch: dict) -> dict:
    before = _outline_node_plan_fields(node)
    fields = patch.get("fields") if isinstance(patch.get("fields"), dict) else patch
    extra = node.extra if isinstance(node.extra, dict) else {}
    next_extra = {**extra}

    opening_hook = fields.get("opening_hook")
    core_event = fields.get("core_event")
    character_change = fields.get("character_change")
    foreshadow = fields.get("foreshadow")
    end_hook = fields.get("end_hook")

    if isinstance(opening_hook, str) and opening_hook.strip():
        node.hook = opening_hook.strip()
    if isinstance(core_event, str) and core_event.strip():
        node.summary = core_event.strip()
    if isinstance(character_change, str) and character_change.strip():
        node.conflict = character_change.strip()
    if isinstance(foreshadow, str):
        next_extra["foreshadow"] = foreshadow.strip()
    if isinstance(end_hook, str) and end_hook.strip():
        node.highlight = end_hook.strip()
        next_extra["end_hook"] = end_hook.strip()

    node.extra = next_extra
    after = _outline_node_plan_fields(node)
    return {
        "chapter_number": patch.get("chapter_number"),
        "node_id": str(node.id) if node.id else None,
        "title": node.title,
        "before": before,
        "after": after,
        "reason": patch.get("reason", ""),
    }


@router.get("/", response_model=List[OutlineNodeOut])
def get_outline_tree(project_id: str, db: Session = Depends(get_db)):
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id
    ).order_by(OutlineNode.sort_order, OutlineNode.created_at).all()
    return build_tree(nodes)


@router.post("/", response_model=OutlineNodeOut, status_code=201)
def create_node(project_id: str, payload: OutlineNodeCreate, db: Session = Depends(get_db)):
    node = OutlineNode(project_id=project_id, **payload.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


@router.patch("/{node_id}", response_model=OutlineNodeOut)
def update_node(project_id: str, node_id: str, payload: OutlineNodeUpdate, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(node, field, value)
    db.commit()
    db.refresh(node)
    return OutlineNodeOut.model_validate(node)


class ChapterPlansClearResult(BaseModel):
    deleted: int


@router.delete("/chapter-plans", response_model=ChapterPlansClearResult)
def delete_all_chapter_plans(project_id: str, db: Session = Depends(get_db)):
    """
    删除项目中全部章节计划（chapter_plan）节点，保留卷 / 篇。
    已绑定大纲的写作章节仅解除 outline_node_id，不删除正文。
    """
    plan_ids = [
        row[0]
        for row in db.query(OutlineNode.id).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "chapter_plan",
        ).all()
    ]
    if not plan_ids:
        return ChapterPlansClearResult(deleted=0)

    db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.outline_node_id.in_(plan_ids),
    ).update({"outline_node_id": None}, synchronize_session=False)

    deleted = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).delete(synchronize_session=False)

    db.commit()
    return ChapterPlansClearResult(deleted=deleted)


@router.delete("/{node_id}", status_code=204)
def delete_node(project_id: str, node_id: str, db: Session = Depends(get_db)):
    node = db.query(OutlineNode).filter(
        OutlineNode.id == node_id, OutlineNode.project_id == project_id
    ).first()
    if not node:
        raise HTTPException(404, "Outline node not found")
    db.delete(node)
    db.commit()


# ─────────────────────────────────────────────────────────────
#  AI 展开大纲（五要素格式）
# ─────────────────────────────────────────────────────────────

class ExpandRequest(BaseModel):
    node_id: str
    chapter_count: int = 10
    model_profile: str = "default"   # default / gemini
    llm_provider_id: Optional[UUID] = None


@router.post("/ai-expand")
async def ai_expand_outline(
    project_id: str,
    req: ExpandRequest,
    db: Session = Depends(get_db),
):
    """
    为指定卷/篇节点 AI 生成详细章节计划（五要素卡片格式），SSE 流式返回。
    生成结果只推送给前端预览，不自动存库——由前端用户确认后调用
    POST /outline/ai-expand/commit 才入库。
    """
    node = db.query(OutlineNode).filter(
        OutlineNode.id == req.node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not node:
        raise HTTPException(404, "Node not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    settings = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    characters = db.query(Character).filter(Character.project_id == project_id).all()

    # 统计当前已有章节数（用于编号连续）
    existing_count = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).count()

    world_summary = " | ".join(f"{s.title}: {(s.content or '')[:80]}" for s in settings[:4])

    def _build_char_summary(char_list: list) -> str:
        """构建角色摘要，区分主线核心与配角层级，并声明「非全量」。"""
        core = [c for c in char_list if (c.character_tier or "core") == "core"]
        supporting = [c for c in char_list if (c.character_tier or "core") != "core"]
        parts = ["以下为主线核心卡司（非全书全部人物，配角可按剧情需要引入）："]
        for c in core[:8]:
            parts.append(
                f"[核心]{c.name}（{c.role}，{c.faction or '无阵营'}）{(c.personality or '')[:40]}"
            )
        for c in supporting[:4]:
            parts.append(
                f"[配角]{c.name}（{c.role}，{c.faction or '无阵营'}）{(c.motivation or '')[:40]}"
            )
        return " | ".join(parts)

    char_summary = _build_char_summary(characters)

    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    genre = (project.genre or "玄幻") if project else "玄幻"

    async def stream():
        yield f"data: {json.dumps({'event': 'start'}, ensure_ascii=False)}\n\n"
        try:
            result = await svc.expand_outline(
                node_title=node.title,
                node_type=node.node_type,
                node_summary=node.summary or "",
                project_title=project.title if project else "未命名",
                genre=genre,
                world_summary=world_summary,
                character_summary=char_summary,
                existing_chapters=existing_count,
                chapter_count=req.chapter_count,
            )
            err_msg = result.get("error") if isinstance(result, dict) else None
            chapters = result.get("chapters") if isinstance(result, dict) else None
            if err_msg or not isinstance(chapters, list) or len(chapters) == 0:
                detail = err_msg or "AI 未返回有效章节列表（可能是模型输出非 JSON 或格式不符）"
                yield f"data: {json.dumps({'event': 'error', 'message': detail}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'event': 'result', 'data': result}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: {\"event\": \"end\"}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─────────────────────────────────────────────────────────────
#  全量生成大纲（卷结构 + 逐卷章节计划）
# ─────────────────────────────────────────────────────────────

class FullGenerateRequest(BaseModel):
    scale_hint: str = "auto"      # micro / auto / short / medium / long / epic — 篇幅倾向，后端按 60 章/卷校准
    theme_statement: Optional[str] = None
    model_profile: str = "default"
    llm_provider_id: Optional[UUID] = None
    clear_existing: bool = False


class OutlineQualityCheckRequest(BaseModel):
    theme_statement: Optional[str] = None
    model_profile: str = "gemini"
    llm_provider_id: Optional[UUID] = None
    scope: Literal["all", "volume", "book"] = "all"
    volume_node_id: Optional[UUID] = None


class OutlineQualityWorkflowStartResponse(BaseModel):
    run_id: str


class OutlineRepairRequest(BaseModel):
    theme_statement: Optional[str] = None
    model_profile: str = "gemini"
    llm_provider_id: Optional[UUID] = None
    scope: Literal["all", "volume", "book"] = "all"
    volume_node_id: Optional[UUID] = None


class OutlineSnapshotRequest(BaseModel):
    label: str = "手动快照"
    note: Optional[str] = None
    scope: Literal["book", "volume"] = "book"
    volume_node_id: Optional[UUID] = None


OutlineProgressPublisher = Callable[[dict[str, Any]], Awaitable[None]]


async def _noop_outline_progress(_: dict[str, Any]) -> None:
    return None


async def _prepare_outline_quality_context(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineQualityCheckRequest = ctx["req"]

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapters = _load_existing_chapter_context(db, project_id, limit=1000)
    if not chapters:
        raise HTTPException(400, "当前项目还没有可质检的章节计划")

    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    theme_statement = (req.theme_statement or story_core.get("theme") or "").strip()

    volume_nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.parent_id.is_(None),
        OutlineNode.node_type == "volume",
    ).order_by(OutlineNode.sort_order).all()
    global_outline_context = _format_global_outline_context([
        (
            node,
            (node.extra or {}).get("target_chapters", TARGET_CHAPTERS_PER_VOLUME)
            if isinstance(node.extra, dict)
            else TARGET_CHAPTERS_PER_VOLUME,
        )
        for node in volume_nodes
    ])

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id,
    ).order_by(WorldSetting.created_at).all()
    characters = db.query(Character).filter(
        Character.project_id == project_id,
    ).order_by(Character.role, Character.created_at).all()
    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
    ).order_by(StoryLine.sort_order, StoryLine.created_at).all()
    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id,
    ).order_by(PowerSystem.sort_order, PowerSystem.created_at).all()
    factions = db.query(Faction).filter(
        Faction.project_id == project_id,
    ).order_by(Faction.sort_order, Faction.created_at).all()
    items = db.query(Item).filter(
        Item.project_id == project_id,
    ).order_by(Item.sort_order, Item.created_at).all()
    skills = db.query(Skill).filter(
        Skill.project_id == project_id,
    ).order_by(Skill.sort_order, Skill.created_at).all()
    foreshadows = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
    ).order_by(Foreshadow.priority.desc(), Foreshadow.created_at).all()

    story_bible_context = _format_outline_quality_story_bible(
        project=project,
        settings=settings,
        characters=characters,
        storylines=storylines,
        power_systems=power_systems,
        factions=factions,
        items=items,
        skills=skills,
        foreshadows=foreshadows,
    )
    book_word_budget_context = _format_outline_word_budget_context(
        target_words=project.target_words,
        chapter_count=len(chapters),
        scope_label="全书",
    )

    return {
        **ctx,
        "project": project,
        "chapters": chapters,
        "theme_statement": theme_statement,
        "volume_nodes": volume_nodes,
        "global_outline_context": global_outline_context,
        "story_bible_context": story_bible_context,
        "book_word_budget_context": book_word_budget_context,
        "volume_reports": [],
    }


async def _quality_check_outline_volumes(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineQualityCheckRequest = ctx["req"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    volume_nodes: list[OutlineNode] = ctx["volume_nodes"]
    if req.volume_node_id:
        volume_nodes = [node for node in volume_nodes if str(node.id) == str(req.volume_node_id)]
        if not volume_nodes:
            raise HTTPException(404, "Volume node not found")
    volume_reports: list[dict] = []

    if not volume_nodes:
        await publish({
            "event": "progress",
            "step": 1,
            "total": 3,
            "label": "未发现卷节点，跳过单卷大纲质检。",
            "done": True,
            "outline_quality_scope": "volume",
        })
        return {**ctx, "volume_reports": []}

    for index, volume in enumerate(volume_nodes, start=1):
        volume_chapters = _load_volume_chapter_context(db, project_id, volume)
        if not volume_chapters:
            await publish({
                "event": "progress",
                "step": index,
                "total": len(volume_nodes),
                "label": f"《{volume.title}》没有章节计划，跳过卷内质检。",
                "done": True,
                "outline_quality_scope": "volume",
                "progress_key": f"outline-quality-volume-{volume.id}",
            })
            continue

        first_number = _chapter_number_value(volume_chapters[0])
        previous_chapters = [
            chapter for chapter in chapters
            if _chapter_number_value(chapter) < first_number
        ]
        await publish({
            "event": "progress",
            "step": index,
            "total": len(volume_nodes),
            "label": f"正在质检《{volume.title}》卷内大纲…",
            "done": False,
            "outline_quality_scope": "volume",
            "progress_key": f"outline-quality-volume-{volume.id}",
        })

        hard_rule_report = _detect_outline_hard_rule_issues(volume_chapters)
        svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
        report = await svc.outline_quality_check(
            project_title=project.title,
            genre=project.genre or "玄幻",
            scope="volume",
            node_title=volume.title,
            node_summary=volume.summary or "",
            theme_statement=ctx["theme_statement"],
            story_bible_context=ctx["story_bible_context"],
            global_outline_context=ctx["global_outline_context"],
            previous_chapters_context=_format_previous_chapters_context(
                previous_chapters,
                max_items=24 if req.model_profile == "gemini" else 8,
            ),
            continuity_state=_format_rolling_continuity_state([
                *previous_chapters[-8:],
                *volume_chapters,
            ]),
            chapters=volume_chapters,
            word_budget_context="\n".join([
                ctx.get("book_word_budget_context", ""),
                _format_outline_word_budget_context(
                    target_words=(
                        ((volume.extra or {}).get("target_chapters") if isinstance(volume.extra, dict) else None)
                        or TARGET_CHAPTERS_PER_VOLUME
                    ) * TARGET_WORDS_PER_CHAPTER,
                    chapter_count=len(volume_chapters),
                    scope_label=f"卷《{volume.title}》",
                ),
            ]),
        )
        report = _merge_outline_quality_reports(report, hard_rule_report)
        volume.extra = _with_outline_quality(volume, report)
        db.add(volume)
        db.commit()
        _create_quality_revision(
            db,
            project_id=project_id,
            scope="volume",
            report=report,
            volume_node=volume,
        )

        volume_report = {
            "node_id": str(volume.id),
            "title": volume.title,
            "report": report,
        }
        volume_reports.append(volume_report)
        await publish({
            "event": "progress",
            "step": index,
            "total": len(volume_nodes),
            "label": _format_outline_quality_label(volume.title, report, "volume"),
            "done": True,
            "error": bool(report.get("error")),
            "outline_quality_scope": "volume",
            "outline_quality_report": report,
            "progress_key": f"outline-quality-volume-{volume.id}",
        })

    return {**ctx, "volume_reports": volume_reports}


async def _quality_check_outline_book(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    req: OutlineQualityCheckRequest = ctx["req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress

    await publish({
        "event": "progress",
        "step": "book",
        "total": "book",
        "label": "正在质检全书大纲…",
        "done": False,
        "outline_quality_scope": "book",
        "progress_key": "outline-quality-book",
    })
    hard_rule_report = _detect_outline_hard_rule_issues(chapters)
    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    report = await svc.outline_quality_check(
        project_title=project.title,
        genre=project.genre or "玄幻",
        scope="book",
        node_title="全书大纲",
        node_summary=project.logline or "",
        theme_statement=ctx["theme_statement"],
        story_bible_context=ctx["story_bible_context"],
        global_outline_context=ctx["global_outline_context"],
        previous_chapters_context="",
        continuity_state=_format_book_quality_continuity_state(chapters),
        chapters=chapters,
        word_budget_context=ctx.get("book_word_budget_context", ""),
    )
    report = _merge_outline_quality_reports(report, hard_rule_report)

    current_core = project.story_core if isinstance(project.story_core, dict) else {}
    project.story_core = {
        **current_core,
        "outline_quality": report,
    }
    db.add(project)
    db.commit()
    _create_quality_revision(
        db,
        project_id=project_id,
        scope="book",
        report=report,
    )

    result = {
        **report,
        "volume_reports": ctx.get("volume_reports", []),
    }
    await publish({
        "event": "progress",
        "step": "book",
        "total": "book",
        "label": _format_outline_quality_label("全书大纲", report, "book"),
        "done": True,
        "error": bool(report.get("error")),
        "outline_quality_scope": "book",
        "outline_quality_report": report,
        "progress_key": "outline-quality-book",
    })
    return {
        **ctx,
        "book_report": report,
        "result": result,
    }


def _relevant_repair_chapters(chapters: list[dict], quality_report: dict) -> list[dict]:
    issue_numbers: set[int] = set()
    for issue in quality_report.get("issues", []) if isinstance(quality_report, dict) else []:
        for number in issue.get("chapter_numbers", []) if isinstance(issue, dict) else []:
            if isinstance(number, int):
                issue_numbers.add(number)
    for number in quality_report.get("must_fix_chapter_numbers", []) if isinstance(quality_report, dict) else []:
        if isinstance(number, int):
            issue_numbers.add(number)
    if not issue_numbers:
        return chapters
    return [chapter for chapter in chapters if _chapter_number_value(chapter) in issue_numbers]


async def _snapshot_outline_before_repair(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label="修复前大纲快照",
        source="pre_repair",
        scope="volume" if req.scope == "volume" else "book",
        volume_node_id=req.volume_node_id if req.scope == "volume" else None,
        note="AI 大纲修复工作流自动保存",
        meta={"repair_scope": req.scope},
    )
    await publish({
        "event": "progress",
        "step": "snapshot_before",
        "label": f"已保存修复前快照：{revision.label}",
        "done": True,
        "revision_id": str(revision.id),
    })
    return {**ctx, "pre_revision_id": str(revision.id)}


async def _build_outline_repair_plan(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    project: Project = ctx["project"]
    chapters: list[dict] = ctx["chapters"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress

    quality_report = ctx.get("book_report") or ctx.get("result") or {}
    if req.scope == "volume":
        reports = ctx.get("volume_reports", [])
        quality_report = reports[0]["report"] if reports else ctx.get("result", {})
        if req.volume_node_id:
            volume = db.query(OutlineNode).filter(
                OutlineNode.id == req.volume_node_id,
                OutlineNode.project_id == project_id,
            ).first()
            if volume:
                chapters = _load_volume_chapter_context(db, project_id, volume)
                if not quality_report:
                    volume_extra = volume.extra if isinstance(volume.extra, dict) else {}
                    quality_report = volume_extra.get("outline_quality") or {}
    elif req.scope == "book":
        if not quality_report:
            project_core = project.story_core if isinstance(project.story_core, dict) else {}
            quality_report = project_core.get("outline_quality") or {}

    relevant_chapters = _relevant_repair_chapters(chapters, quality_report)
    await publish({
        "event": "progress",
        "step": "repair_plan",
        "label": f"正在生成修复补丁（{len(relevant_chapters)} 个相关章节）…",
        "done": False,
    })
    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)
    repair_plan = await svc.outline_repair_plan(
        project_title=project.title,
        genre=project.genre or "玄幻",
        scope=req.scope,
        quality_report=quality_report,
        chapters=relevant_chapters,
        story_bible_context=ctx["story_bible_context"],
        global_outline_context=ctx["global_outline_context"],
        word_budget_context=_format_outline_word_budget_context(
            target_words=project.target_words,
            chapter_count=len(chapters if req.scope == "book" else relevant_chapters),
            scope_label="修复范围",
        ),
    )
    await publish({
        "event": "progress",
        "step": "repair_plan",
        "label": repair_plan.get("summary") or f"修复补丁生成完成：{len(repair_plan.get('patches', []))} 条",
        "done": True,
        "error": bool(repair_plan.get("error")),
        "repair_plan": repair_plan,
    })
    return {**ctx, "repair_plan": repair_plan, "repair_quality_report": quality_report}


async def _apply_outline_repair_plan(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    repair_plan = ctx.get("repair_plan") or {}
    patches = repair_plan.get("patches") if isinstance(repair_plan, dict) else []
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    nodes = db.query(OutlineNode).filter(
        OutlineNode.project_id == project_id,
        OutlineNode.node_type == "chapter_plan",
    ).all()
    by_number = {
        _outline_node_to_chapter_context(node).get("number"): node
        for node in nodes
    }
    records = []
    for patch in patches if isinstance(patches, list) else []:
        if not isinstance(patch, dict):
            continue
        node = by_number.get(patch.get("chapter_number"))
        if not node:
            continue
        records.append(_apply_outline_patch_to_node(node, patch))
        db.add(node)
    db.commit()
    await publish({
        "event": "progress",
        "step": "apply_patches",
        "label": f"已应用 {len(records)} 条大纲修复补丁",
        "done": True,
        "applied_patches": records,
    })
    return {**ctx, "applied_patches": records}


async def _snapshot_outline_after_repair(ctx: dict[str, Any]) -> dict[str, Any]:
    db: Session = ctx["db"]
    project_id: str = ctx["project_id"]
    req: OutlineRepairRequest = ctx["repair_req"]
    publish: OutlineProgressPublisher = ctx.get("publish") or _noop_outline_progress
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label="修复后大纲快照",
        source="post_repair",
        scope="volume" if req.scope == "volume" else "book",
        volume_node_id=req.volume_node_id if req.scope == "volume" else None,
        note="AI 大纲修复工作流自动保存",
        meta={
            "repair_scope": req.scope,
            "pre_revision_id": ctx.get("pre_revision_id"),
            "applied_patches": ctx.get("applied_patches", []),
            "repair_plan": ctx.get("repair_plan", {}),
        },
    )
    result = {
        "scope": req.scope,
        "status": "done",
        "summary": f"已应用 {len(ctx.get('applied_patches', []))} 条大纲修复补丁",
        "pre_revision_id": ctx.get("pre_revision_id"),
        "post_revision_id": str(revision.id),
        "applied_patches": ctx.get("applied_patches", []),
        "repair_plan": ctx.get("repair_plan", {}),
    }
    await publish({
        "event": "progress",
        "step": "snapshot_after",
        "label": f"已保存修复后快照：{revision.label}",
        "done": True,
        "revision_id": str(revision.id),
    })
    return {**ctx, "post_revision_id": str(revision.id), "result": result}


def _outline_quality_nodes_for_scope(scope: str) -> list[WorkflowNode]:
    nodes = [
        WorkflowNode("prepare_outline_context", "读取大纲与故事圣经账本", _prepare_outline_quality_context),
    ]
    if scope in {"all", "volume"}:
        nodes.append(WorkflowNode("quality_check_volumes", "单卷大纲质检并写回卷节点", _quality_check_outline_volumes))
    if scope in {"all", "book"}:
        nodes.append(WorkflowNode("quality_check_book", "全书大纲质检并写回项目", _quality_check_outline_book))
    return nodes


async def _finalize_outline_quality_result(ctx: dict[str, Any]) -> dict[str, Any]:
    req: OutlineQualityCheckRequest = ctx["req"]
    if req.scope == "book":
        return ctx
    if req.scope == "volume":
        reports = ctx.get("volume_reports", [])
        if len(reports) == 1:
            return {
                **ctx,
                "result": {
                    **reports[0]["report"],
                    "node_id": reports[0]["node_id"],
                    "title": reports[0]["title"],
                },
            }
        return {
            **ctx,
            "result": {
                "scope": "volume",
                "status": "pass" if reports else "warning",
                "summary": f"完成 {len(reports)} 个卷节点质检。",
                "volume_reports": reports,
            },
        }
    return ctx


async def _execute_outline_quality_graph(ctx: dict[str, Any]) -> dict[str, Any]:
    req: OutlineQualityCheckRequest = ctx["req"]
    graph = WorkflowGraph([
        *_outline_quality_nodes_for_scope(req.scope),
        WorkflowNode("finalize_outline_quality_result", "整理大纲质检结果", _finalize_outline_quality_result),
    ])
    current = dict(ctx)
    for node in graph.nodes:
        result = node.handler(current)
        if hasattr(result, "__await__"):
            result = await result  # type: ignore[assignment]
        if isinstance(result, dict):
            current = result
    return current


async def _run_outline_quality_workflow(run_id: str, project_id: str, req_payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        req = OutlineQualityCheckRequest(**req_payload)

        async def publish(event: dict[str, Any]) -> None:
            await workflow_runs.publish(run_id, event)

        graph = WorkflowGraph([
            *_outline_quality_nodes_for_scope(req.scope),
            WorkflowNode("finalize_outline_quality_result", "整理大纲质检结果", _finalize_outline_quality_result),
        ])
        await workflow_runs.run_graph(run_id, graph, {
            "db": db,
            "project_id": project_id,
            "req": req,
            "publish": publish,
        })
    finally:
        db.close()


async def _run_outline_repair_workflow(run_id: str, project_id: str, req_payload: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        repair_req = OutlineRepairRequest(**req_payload)
        quality_req = OutlineQualityCheckRequest(**req_payload)

        async def publish(event: dict[str, Any]) -> None:
            await workflow_runs.publish(run_id, event)

        graph = WorkflowGraph([
            WorkflowNode("snapshot_before_repair", "保存修复前大纲快照", _snapshot_outline_before_repair),
            WorkflowNode("prepare_outline_context_for_repair", "读取大纲与故事圣经账本（供修复补丁）", _prepare_outline_quality_context),
            WorkflowNode("build_outline_repair_plan", "生成大纲修复补丁", _build_outline_repair_plan),
            WorkflowNode("apply_outline_repair_plan", "应用大纲修复补丁", _apply_outline_repair_plan),
            WorkflowNode("snapshot_after_repair", "保存修复后大纲快照", _snapshot_outline_after_repair),
            *_outline_quality_nodes_for_scope(repair_req.scope),
            WorkflowNode("finalize_outline_quality_result", "整理修复后质检结果", _finalize_outline_quality_result),
        ])
        await workflow_runs.run_graph(run_id, graph, {
            "db": db,
            "project_id": project_id,
            "req": quality_req,
            "repair_req": repair_req,
            "publish": publish,
        })
    finally:
        db.close()


@router.post("/ai-full-generate")
async def ai_full_generate_outline(
    project_id: str,
    req: FullGenerateRequest,
    db: Session = Depends(get_db),
):
    """
    全量生成大纲：AI 规划卷结构，后端按「每卷约 60 章」校准章节数。
      Step 0（可选）：清除现有大纲
      Step 1：AI 分析故事，规划卷级骨架（含每卷 planned_chapters），写入数据库
      Step 2~N：逐卷按 planned_chapters 生成章节计划，写入数据库
    全程 SSE 推送进度，边生成边持久化。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    settings_list = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    characters = db.query(Character).filter(Character.project_id == project_id).all()

    world_summary = " | ".join(
        f"{s.title}: {(s.content or '')[:80]}" for s in settings_list[:4]
    )
    char_summary = " | ".join(
        f"{c.name}（{c.role}，{c.faction or ''}）{(c.personality or '')[:40]}"
        for c in characters[:5]
    )
    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    theme_statement = (req.theme_statement or story_core.get("theme") or "").strip()

    svc = AIService(profile=req.model_profile, db=db, llm_provider_id=req.llm_provider_id)

    # ── 共用：按批次为单个节点生成并写入章节计划 ──────────────
    async def fill_node_with_chapters(
        target_node: OutlineNode,
        planned_chapters: int,
        chapter_offset: int,
        step: int,
        total_steps: int,
        global_outline_context: str = "",
        prior_chapters: list[dict] | None = None,
    ):
        """
        为 target_node（卷或篇）生成章节计划并入库。
        target_node 为卷/旧篇时直接挂章节，不再自动创建篇。
        返回 (写入章节数, 新的 chapter_offset)。
        以 async generator 推送进度 SSE。
        """
        BATCH_SIZE = _outline_batch_size(req.model_profile)
        batches: list[int] = []
        remaining = planned_chapters
        while remaining > 0:
            batches.append(min(remaining, BATCH_SIZE))
            remaining -= BATCH_SIZE

        all_chapters: list[dict] = []
        batch_error = False
        batch_error_messages: list[str] = []

        for batch_idx, batch_count in enumerate(batches):
            batch_offset = chapter_offset + len(all_chapters)
            previous_context_limit = 24 if req.model_profile == "gemini" else 8
            context_chapters = [*(prior_chapters or []), *all_chapters]
            previous_chapters_context = _format_previous_chapters_context(
                context_chapters,
                max_items=previous_context_limit,
            )
            continuity_state = _format_rolling_continuity_state(context_chapters)
            batch_goal = _format_outline_batch_goal(
                node_title=target_node.title,
                batch_offset=batch_offset,
                batch_count=batch_count,
                planned_chapters=planned_chapters,
                node_generated_chapters=len(all_chapters),
            )
            try:
                result = await svc.expand_outline(
                    node_title=target_node.title,
                    node_type=target_node.node_type,
                    node_summary=target_node.summary or "",
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    theme_statement=theme_statement,
                    existing_chapters=batch_offset,
                    chapter_count=batch_count,
                    global_outline_context=global_outline_context,
                    previous_chapters_context=previous_chapters_context,
                    continuity_state=continuity_state,
                    batch_goal=batch_goal,
                )
                batch_chapters = [
                    _sanitize_generated_outline_chapter(ch, project.genre)
                    for ch in (result.get("chapters", []) or [])
                    if isinstance(ch, dict)
                ]
                if not batch_chapters:
                    detail = result.get("error") or result.get("raw") or "AI 未返回 chapters 数组"
                    batch_error = True
                    batch_error_messages.append(str(detail)[:180])
                    yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批无有效章节：{str(detail)[:120]}', 'error': True}, ensure_ascii=False)}\n\n"
                else:
                    all_chapters.extend(batch_chapters)
                    if len(batches) > 1:
                        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}/{len(batches)}批完成（+{len(batch_chapters)} 章）'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》第{batch_idx+1}批失败：{str(e)}', 'error': True}, ensure_ascii=False)}\n\n"
                batch_error = True
                batch_error_messages.append(str(e)[:180])

        if not all_chapters:
            reason = f"；原因：{batch_error_messages[-1]}" if batch_error_messages else ""
            yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》未获得有效章节，已跳过{reason}', 'error': True, 'done': True}, ensure_ascii=False)}\n\n"
            yield 0   # 用 yield 传回写入数量（async generator 不能 return value）
            return

        for ci, ch in enumerate(all_chapters):
            db.add(OutlineNode(
                project_id=project_id,
                parent_id=target_node.id,
                node_type="chapter_plan",
                title=f"第{ch.get('number', chapter_offset + ci + 1)}章：{ch.get('title', '未命名')}",
                summary=ch.get("core_event"),
                hook=ch.get("opening_hook"),
                highlight=ch.get("end_hook"),
                conflict=ch.get("character_change"),
                sort_order=ci,
                extra={
                    "foreshadow":    ch.get("foreshadow", ""),
                    "pacing":        ch.get("pacing", "medium"),
                    "word_estimate": ch.get("word_estimate", TARGET_WORDS_PER_CHAPTER),
                    "end_hook":      ch.get("end_hook", ""),
                },
            ))
        db.flush()
        db.commit()

        warn = "（部分批次失败）" if batch_error else ""
        yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'《{target_node.title}》完成{warn}，写入 {len(all_chapters)} 章', 'done': True}, ensure_ascii=False)}\n\n"
        yield {"generated_chapters": all_chapters}
        yield len(all_chapters)   # 最后 yield int，调用方接收后不转发给客户端

    # ── 判断走哪条路 ─────────────────────────────────
    def get_expandable_nodes() -> list[OutlineNode]:
        """
        收集已有大纲中尚无章节计划的节点。
        优先返回没有直接章节计划的卷；旧篇节点保留兼容展开。
        """
        existing_vols = db.query(OutlineNode).filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id.is_(None),
            OutlineNode.node_type == "volume",
        ).order_by(OutlineNode.sort_order).all()

        expandable: list[OutlineNode] = []
        for vol in existing_vols:
            arcs = db.query(OutlineNode).filter(
                OutlineNode.parent_id == vol.id,
                OutlineNode.node_type == "arc",
            ).order_by(OutlineNode.sort_order).all()

            if arcs:
                for arc in arcs:
                    has_chapters = db.query(OutlineNode).filter(
                        OutlineNode.parent_id == arc.id,
                        OutlineNode.node_type == "chapter_plan",
                    ).count() > 0
                    if not has_chapters:
                        expandable.append(arc)
            else:
                has_chapters = db.query(OutlineNode).filter(
                    OutlineNode.parent_id == vol.id,
                    OutlineNode.node_type == "chapter_plan",
                ).count() > 0
                if not has_chapters:
                    expandable.append(vol)

        return expandable

    # scale_hint → 续写模式默认章节数；规划模式会按总篇幅目标校准。
    _default_chapters = TARGET_CHAPTERS_PER_VOLUME

    async def stream():
        # ── Step 0: 清除现有大纲（可选）──────────────────
        if req.clear_existing:
            db.query(Chapter).filter(
                Chapter.project_id == project_id
            ).update({"outline_node_id": None}, synchronize_session=False)
            db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id
            ).delete(synchronize_session=False)
            db.commit()
            yield f"data: {json.dumps({'event': 'progress', 'step': 0, 'total': '?', 'label': '已清除现有大纲（章节正文已保留）', 'done': True}, ensure_ascii=False)}\n\n"

        # ── 分叉：续写模式 vs. 规划模式 ──────────────────
        expandable = get_expandable_nodes()
        use_fill_mode = (not req.clear_existing) and len(expandable) > 0

        if use_fill_mode:
            # ════════════════════════════════════════════
            #  续写模式：直接填充已有空卷/旧篇，不新建卷
            # ════════════════════════════════════════════
            total_steps = len(expandable)
            names = "、".join(f"《{n.title}》" for n in expandable)
            yield f"data: {json.dumps({'event': 'progress', 'step': 0, 'total': total_steps, 'label': f'发现 {len(expandable)} 个空节点，开始续写：{names}', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()
            root_volumes = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.parent_id.is_(None),
                OutlineNode.node_type == "volume",
            ).order_by(OutlineNode.sort_order).all()
            global_outline_context = _format_global_outline_context([
                (
                    node,
                    (node.extra or {}).get("target_chapters", _default_chapters)
                    if isinstance(node.extra, dict)
                    else _default_chapters,
                )
                for node in (root_volumes or expandable)
            ])
            existing_context_limit = 24 if req.model_profile == "gemini" else 8
            book_chapters_so_far = _load_existing_chapter_context(
                db,
                project_id,
                limit=existing_context_limit,
            )

            total_written = 0
            for step_i, target in enumerate(expandable):
                yield f"data: {json.dumps({'event': 'progress', 'step': step_i + 1, 'total': total_steps, 'label': f'正在展开《{target.title}》…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    target, _default_chapters, chapter_offset,
                    step=step_i + 1, total_steps=total_steps,
                    global_outline_context=global_outline_context,
                    prior_chapters=book_chapters_so_far,
                ):
                    if isinstance(chunk, int):
                        written = chunk
                    elif isinstance(chunk, dict) and "generated_chapters" in chunk:
                        book_chapters_so_far = [
                            *book_chapters_so_far,
                            *chunk["generated_chapters"],
                        ]
                    else:
                        yield chunk
                chapter_offset += written
                total_written += written

            yield f"data: {json.dumps({'event': 'complete', 'message': f'续写完成！共为 {len(expandable)} 个节点写入 {total_written} 章'}, ensure_ascii=False)}\n\n"
            yield "data: {\"event\": \"end\"}\n\n"

        else:
            # ════════════════════════════════════════════
            #  规划模式：AI 从零规划卷结构，建卷再填章节
            # ════════════════════════════════════════════
            yield f"data: {json.dumps({'event': 'progress', 'step': 1, 'total': '?', 'label': 'AI 正在分析故事，规划卷章结构…'}, ensure_ascii=False)}\n\n"

            try:
                structure = await svc.plan_full_structure(
                    project_title=project.title,
                    genre=project.genre or "玄幻",
                    logline=project.logline or "",
                    world_summary=world_summary,
                    character_summary=char_summary,
                    theme_statement=theme_statement,
                    scale_hint=req.scale_hint,
                )
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'message': f'结构规划失败：{str(e)}'}, ensure_ascii=False)}\n\n"
                return

            if "error" in structure:
                yield f"data: {json.dumps({'event': 'error', 'message': structure['error']}, ensure_ascii=False)}\n\n"
                return

            volumes_data = structure.get("volumes", [])
            if not volumes_data:
                yield f"data: {json.dumps({'event': 'error', 'message': 'AI 未返回有效的卷结构，请重试'}, ensure_ascii=False)}\n\n"
                return

            volumes_data = normalize_volume_plan(volumes_data, req.scale_hint)

            total_steps = 1 + len(volumes_data)
            total_chapters_planned = sum(v["planned_chapters"] for v in volumes_data)

            existing_vol_count = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.parent_id.is_(None),
            ).count()

            volume_nodes: list[tuple[OutlineNode, int]] = []
            for i, vol in enumerate(volumes_data):
                node = OutlineNode(
                    project_id=project_id,
                    parent_id=None,
                    node_type="volume",
                    title=vol.get("title", f"第{existing_vol_count + i + 1}卷"),
                    summary=vol.get("summary", ""),
                    hook=vol.get("hook", ""),
                    conflict=vol.get("conflict", ""),
                    extra={
                        "theme_stage": vol.get("theme_stage", ""),
                        "character_arc": vol.get("character_arc", ""),
                        "target_chapters": TARGET_CHAPTERS_PER_VOLUME,
                        "target_words_per_chapter": TARGET_WORDS_PER_CHAPTER,
                    },
                    sort_order=existing_vol_count + i,
                )
                db.add(node)
                db.flush()
                volume_nodes.append((node, vol["planned_chapters"]))
            db.commit()

            vol_summary = "、".join(f"《{n.title}》{pc}章" for n, pc in volume_nodes)
            global_outline_context = _format_global_outline_context(volume_nodes)
            yield f"data: {json.dumps({'event': 'progress', 'step': 1, 'total': total_steps, 'label': f'结构规划完成：{vol_summary}，共 {total_chapters_planned} 章', 'done': True}, ensure_ascii=False)}\n\n"

            chapter_offset = db.query(OutlineNode).filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            ).count()
            existing_context_limit = 24 if req.model_profile == "gemini" else 8
            book_chapters_so_far = _load_existing_chapter_context(
                db,
                project_id,
                limit=existing_context_limit,
            )

            total_written = 0
            for vi, (vol_node, planned_chapters) in enumerate(volume_nodes):
                step = vi + 2
                yield f"data: {json.dumps({'event': 'progress', 'step': step, 'total': total_steps, 'label': f'正在展开《{vol_node.title}》（{planned_chapters} 章）…'}, ensure_ascii=False)}\n\n"
                written = 0
                async for chunk in fill_node_with_chapters(
                    vol_node, planned_chapters, chapter_offset,
                    step=step, total_steps=total_steps,
                    global_outline_context=global_outline_context,
                    prior_chapters=book_chapters_so_far,
                ):
                    if isinstance(chunk, int):
                        written = chunk
                    elif isinstance(chunk, dict) and "generated_chapters" in chunk:
                        book_chapters_so_far = [
                            *book_chapters_so_far,
                            *chunk["generated_chapters"],
                        ]
                    else:
                        yield chunk
                chapter_offset += written
                total_written += written

            yield f"data: {json.dumps({'event': 'complete', 'message': f'全量大纲生成完成！共 {len(volume_nodes)} 卷 {total_written} 章'}, ensure_ascii=False)}\n\n"
            yield "data: {\"event\": \"end\"}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/ai-quality-check")
async def ai_quality_check_outline(
    project_id: str,
    req: OutlineQualityCheckRequest,
    db: Session = Depends(get_db),
):
    """
    独立大纲质检接口：读取当前已入库的大纲章节计划，先逐卷质检并写回卷节点，
    再做全书级质检并写回项目 story_core。
    与全量生成拆开，避免生成失败和质检失败互相污染。
    """
    result_context = await _execute_outline_quality_graph({
        "db": db,
        "project_id": project_id,
        "req": req,
        "publish": _noop_outline_progress,
    })
    return result_context["result"]


@router.post("/ai-quality-check/workflow", response_model=OutlineQualityWorkflowStartResponse)
async def start_ai_quality_check_outline_workflow(
    project_id: str,
    req: OutlineQualityCheckRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start the graph-backed outline QA workflow.
    Progress is delivered through:
    /api/v1/projects/{project_id}/outline/workflows/{run_id}/ws
    """
    run_id = await workflow_runs.create_run(
        "outline_quality_check",
        {
            "project_id": project_id,
            "model_profile": req.model_profile,
        },
    )
    background_tasks.add_task(
        _run_outline_quality_workflow,
        run_id,
        project_id,
        req.model_dump(mode="json"),
    )
    return OutlineQualityWorkflowStartResponse(run_id=run_id)


@router.post("/ai-repair/workflow", response_model=OutlineQualityWorkflowStartResponse)
async def start_ai_repair_outline_workflow(
    project_id: str,
    req: OutlineRepairRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start the graph-backed outline repair workflow.
    It creates pre/post outline revisions and streams progress over the same
    workflow WebSocket endpoint.
    """
    run_id = await workflow_runs.create_run(
        "outline_repair",
        {
            "project_id": project_id,
            "model_profile": req.model_profile,
            "scope": req.scope,
        },
    )
    background_tasks.add_task(
        _run_outline_repair_workflow,
        run_id,
        project_id,
        req.model_dump(mode="json"),
    )
    return OutlineQualityWorkflowStartResponse(run_id=run_id)


@router.get("/revisions")
def list_outline_revisions(project_id: str, db: Session = Depends(get_db)):
    revisions = db.query(OutlineRevision).filter(
        OutlineRevision.project_id == project_id,
    ).order_by(OutlineRevision.created_at.desc()).limit(50).all()
    return [
        {
            "id": str(rev.id),
            "label": rev.label,
            "source": rev.source,
            "scope": rev.scope,
            "volume_node_id": str(rev.volume_node_id) if rev.volume_node_id else None,
            "note": rev.note,
            "node_count": rev.node_count,
            "meta": rev.meta or {},
            "created_at": rev.created_at.isoformat() if rev.created_at else None,
        }
        for rev in revisions
    ]


@router.get("/revisions/{revision_id}")
def get_outline_revision(project_id: str, revision_id: str, db: Session = Depends(get_db)):
    revision = db.query(OutlineRevision).filter(
        OutlineRevision.id == revision_id,
        OutlineRevision.project_id == project_id,
    ).first()
    if not revision:
        raise HTTPException(404, "Outline revision not found")
    return {
        "id": str(revision.id),
        "label": revision.label,
        "source": revision.source,
        "scope": revision.scope,
        "volume_node_id": str(revision.volume_node_id) if revision.volume_node_id else None,
        "note": revision.note,
        "node_count": revision.node_count,
        "meta": revision.meta or {},
        "snapshot": revision.snapshot,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }


@router.post("/revisions")
def create_outline_revision(project_id: str, req: OutlineSnapshotRequest, db: Session = Depends(get_db)):
    revision = _create_outline_revision(
        db,
        project_id=project_id,
        label=req.label,
        source="manual",
        scope=req.scope,
        volume_node_id=req.volume_node_id,
        note=req.note,
    )
    return {
        "id": str(revision.id),
        "label": revision.label,
        "source": revision.source,
        "scope": revision.scope,
        "volume_node_id": str(revision.volume_node_id) if revision.volume_node_id else None,
        "note": revision.note,
        "node_count": revision.node_count,
        "meta": revision.meta or {},
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
    }


@router.websocket("/workflows/{run_id}/ws")
async def outline_workflow_websocket(
    project_id: str,
    run_id: str,
    websocket: WebSocket,
):
    await workflow_runs.stream_to_websocket(run_id, websocket)


class CommitExpandRequest(BaseModel):
    parent_node_id: str
    chapters: List[dict]   # 前端确认后传回的章节列表


@router.post("/ai-expand/commit", response_model=List[OutlineNodeOut])
def commit_expand(
    project_id: str,
    req: CommitExpandRequest,
    db: Session = Depends(get_db),
):
    """
    把前端确认的章节计划批量写入大纲树。
    直接把章节计划挂到选中的卷或旧篇节点下；新生成不再创建篇节点。
    """
    parent = db.query(OutlineNode).filter(
        OutlineNode.id == req.parent_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not parent:
        raise HTTPException(404, "Parent node not found")

    results = []
    project = db.query(Project).filter(Project.id == project_id).first()
    genre = project.genre if project else None
    for i, ch in enumerate(req.chapters):
        safe_ch = _sanitize_generated_outline_chapter(ch, genre) if isinstance(ch, dict) else {}
        node = OutlineNode(
            project_id=project_id,
            parent_id=parent.id,
            node_type="chapter_plan",
            title=f"第{safe_ch.get('number', i + 1)}章：{safe_ch.get('title', '未命名')}",
            summary=safe_ch.get("core_event"),
            hook=safe_ch.get("opening_hook"),
            highlight=safe_ch.get("end_hook"),    # 章末钩子放 highlight 字段
            conflict=safe_ch.get("character_change"),
            sort_order=i,
            extra={
                "foreshadow":    safe_ch.get("foreshadow", ""),
                "pacing":        safe_ch.get("pacing", "medium"),
                "word_estimate": safe_ch.get("word_estimate", TARGET_WORDS_PER_CHAPTER),
                "end_hook":      safe_ch.get("end_hook", ""),
            },
        )
        db.add(node)
        db.flush()
        results.append(node)

    db.commit()
    return [OutlineNodeOut.model_validate(n) for n in results]
