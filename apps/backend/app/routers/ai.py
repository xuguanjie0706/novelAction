from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel
from typing import Optional, List, Literal
from uuid import UUID
import json
import re

from app.database import get_db
from app.models import (
    Chapter,
    MemoryChunk,
    Project,
    WorldSetting,
    Character,
    ChapterIndex,
    OutlineNode,
    StoryLine,
    PowerSystem,
    ChapterCoherenceReport,
    Foreshadow,
)
from app.schemas import MemoryChunkCreate, MemoryChunkOut
from app.services.ai_service import AIService

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])

_ALLOWED_CHARACTER_STATUS = {"alive", "dead", "missing", "sealed", "transformed"}
_ALLOWED_STORYLINE_STATUS = {"planned", "active", "climax", "resolved", "dropped"}


def _plain_text(html: str | None) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _truncate(text: str | None, limit: int) -> str:
    clean = (text or "").strip()
    return clean[:limit]


def _normalize_character_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    token = re.split(r"[\s（(，,;；。!！]", text, maxsplit=1)[0]
    alias = {
        "normal": "alive",
        "living": "alive",
        "active": "alive",
        "deaded": "dead",
        "deceased": "dead",
    }
    candidate = alias.get(token, token)
    if candidate in _ALLOWED_CHARACTER_STATUS:
        return candidate
    if "dead" in text or "死亡" in text:
        return "dead"
    if "missing" in text or "失踪" in text:
        return "missing"
    if "sealed" in text or "封印" in text:
        return "sealed"
    if "transform" in text or "变身" in text or "异化" in text:
        return "transformed"
    if "alive" in text or "存活" in text or "生还" in text or "活着" in text:
        return "alive"
    return None


def _normalize_storyline_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    token = re.split(r"[\s（(，,;；。!！]", raw.strip().lower(), maxsplit=1)[0]
    if token in _ALLOWED_STORYLINE_STATUS:
        return token
    return None


def _existing_foreshadow_codes(db: Session, project_id: str) -> set[str]:
    rows = db.query(Foreshadow.code).filter(Foreshadow.project_id == project_id).all()
    codes = set()
    for row in rows:
        try:
            code = row[0]
        except Exception:
            code = row
        if code:
            codes.add(str(code).strip())
    return codes


def _next_foreshadow_code(db: Session, project_id: str, reserved_codes: Optional[set[str]] = None) -> str:
    used_codes = _existing_foreshadow_codes(db, project_id)
    if reserved_codes:
        used_codes = used_codes | reserved_codes
    max_number = 0
    for code in used_codes:
        match = re.search(r"\bF[-_ ]?(\d{1,4})\b", code, flags=re.IGNORECASE)
        if match:
            max_number = max(max_number, int(match.group(1)))
    next_number = max_number + 1
    while f"F-{next_number:03d}" in used_codes:
        next_number += 1
    return f"F-{next_number:03d}"


def _foreshadow_payload_from_index_item(item: dict, default_status: str = "open") -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    raw = (
        item.get("description")
        or item.get("title")
        or item.get("content")
        or item.get("note")
        or ""
    )
    text = str(raw).strip()
    if not text:
        return None

    code = None
    code_match = re.search(r"\bF[-_ ]?(\d{1,4})\b", text, flags=re.IGNORECASE)
    if code_match:
        code = f"F-{int(code_match.group(1)):03d}"

    description = re.sub(
        r"^\s*F[-_ ]?\d{1,4}\s*[:：\-—]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    description = description or text

    planned_action = str(item.get("planned_action") or "").strip().lower()
    if planned_action not in {"resolve", "develop"}:
        planned_action = "develop" if "铺垫" in text else "resolve"

    planned_resolve_chapter = item.get("planned_resolve_chapter")
    if planned_resolve_chapter is None:
        planned_match = re.search(
            r"(?:ch[_-]?0*(\d+)|第\s*(\d+)\s*章)[^。；;，,）)]{0,12}(回收|铺垫)",
            text,
            flags=re.IGNORECASE,
        )
        if planned_match:
            planned_resolve_chapter = int(planned_match.group(1) or planned_match.group(2))
            planned_action = "develop" if planned_match.group(3) == "铺垫" else "resolve"
    else:
        try:
            planned_resolve_chapter = int(planned_resolve_chapter)
        except Exception:
            planned_resolve_chapter = None

    title = re.sub(
        r"[（(]\s*(?:ch[_-]?0*\d+|第\s*\d+\s*章)[^）)]*(?:回收|铺垫)\s*[）)]",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip(" ：:，,。；;")
    title = str(item.get("title") or title or description).strip()[:200]

    raw_status = str(item.get("status") or default_status or "open").strip().lower()
    status = raw_status if raw_status in {"open", "resolved", "dropped"} else "open"

    return {
        "code": code,
        "title": title,
        "description": description,
        "planned_resolve_chapter": planned_resolve_chapter,
        "planned_action": planned_action,
        "status": status,
    }


def _sync_chapter_index_foreshadows(
    db: Session,
    project_id: str,
    chapter: Chapter,
    chapter_index: "ChapterIndexPayload",
) -> dict:
    """Mirror actual chapter-index foreshadows into the global tracking table."""
    stats = {"created": 0, "updated": 0, "resolved": 0}
    chapter_number = chapter.sort_order + 1
    reserved_codes: set[str] = set()

    def find_existing(payload: dict) -> Optional[Foreshadow]:
        q = db.query(Foreshadow).filter(Foreshadow.project_id == project_id)
        if payload.get("code"):
            existing = q.filter(Foreshadow.code == payload["code"]).first()
            if existing:
                return existing
        return q.filter(
            Foreshadow.title == payload["title"],
            Foreshadow.laid_chapter_id == chapter.id,
        ).first()

    for item in chapter_index.actual_foreshadows_laid or []:
        payload = _foreshadow_payload_from_index_item(item, default_status="open")
        if not payload:
            continue
        existing = find_existing(payload)
        if existing:
            existing.title = payload["title"]
            existing.description = payload["description"]
            existing.laid_chapter_id = existing.laid_chapter_id or chapter.id
            existing.laid_chapter_number = existing.laid_chapter_number or chapter_number
            if payload.get("planned_resolve_chapter"):
                existing.planned_resolve_chapter = payload["planned_resolve_chapter"]
                existing.planned_action = payload["planned_action"]
            if existing.status != "resolved":
                existing.status = payload["status"]
            stats["updated"] += 1
            continue

        code = payload["code"] or _next_foreshadow_code(db, project_id, reserved_codes)
        reserved_codes.add(code)
        db.add(Foreshadow(
            project_id=project_id,
            code=code,
            title=payload["title"],
            description=payload["description"],
            laid_chapter_id=chapter.id,
            laid_chapter_number=chapter_number,
            planned_resolve_chapter=payload.get("planned_resolve_chapter"),
            planned_action=payload["planned_action"],
            status=payload["status"],
            priority=3,
        ))
        stats["created"] += 1

    for item in chapter_index.actual_foreshadows_resolved or []:
        payload = _foreshadow_payload_from_index_item(item, default_status="resolved")
        if not payload:
            continue
        existing = find_existing(payload)
        if existing:
            existing.status = "resolved"
            existing.resolved_chapter_id = chapter.id
            existing.resolved_chapter_number = chapter_number
            if payload.get("description"):
                existing.description = payload["description"]
            stats["resolved"] += 1
            continue

        code = payload["code"] or _next_foreshadow_code(db, project_id, reserved_codes)
        reserved_codes.add(code)
        db.add(Foreshadow(
            project_id=project_id,
            code=code,
            title=payload["title"],
            description=payload["description"],
            resolved_chapter_id=chapter.id,
            resolved_chapter_number=chapter_number,
            planned_action="resolve",
            status="resolved",
            priority=3,
        ))
        stats["created"] += 1
        stats["resolved"] += 1

    return stats


def _build_continuity_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
) -> str:
    """生成前的跨章事实账本：状态、伏笔、承接点、禁止事项。"""
    current_chapter_number = chapter.sort_order + 1
    previous_chapter_number = max(chapter.sort_order, 0)

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).order_by(Character.role, Character.name).all()
    char_lines = []
    for c in characters[:10]:
        parts = [f"{c.name}"]
        if c.role:
            parts.append(f"身份={c.role}")
        if c.current_realm:
            parts.append(f"当前境界={c.current_realm}")
        if c.realm_rank is not None:
            parts.append(f"境界序号={c.realm_rank}")
        if c.current_location:
            parts.append(f"当前位置={c.current_location}")
        if c.current_status and c.current_status != "alive":
            parts.append(f"状态={c.current_status}")
        char_lines.append("、".join(parts))

    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).order_by(PowerSystem.sort_order).all()
    power_lines = []
    for ps in power_systems[:3]:
        level_names = []
        for level in (ps.levels or [])[:8]:
            if isinstance(level, dict) and level.get("name"):
                rank = level.get("rank")
                level_names.append(f"{rank}.{level.get('name')}" if rank else level.get("name"))
        rule = _truncate(ps.special_rules or ps.breakthrough_condition or ps.description, 80)
        line = f"{ps.name}"
        if level_names:
            line += f"等级顺序={' > '.join(level_names)}"
        if ps.protagonist_current_rank:
            line += f"；主角当前rank={ps.protagonist_current_rank}"
        if rule:
            line += f"；规则={rule}"
        power_lines.append(line)

    recent_chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).limit(3).all()
    recent_lines = []
    for c in reversed(recent_chapters):
        source = getattr(c, "summary", None) or _plain_text(c.content)[-180:]
        if source:
            recent_lines.append(f"第{c.sort_order + 1}章《{c.title}》：{_truncate(source, 160)}")

    foreshadow_memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id,
        MemoryChunk.memory_type.in_(["foreshadow", "event", "character_state"]),
    ).order_by(MemoryChunk.chapter_number.desc()).limit(8).all()
    memory_lines = [
        f"第{m.chapter_number or '?'}章 {m.title or m.memory_type}：{_truncate(m.content, 100)}"
        for m in foreshadow_memories
        if (m.content or "").strip()
    ]

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"]),
    ).order_by(StoryLine.sort_order).limit(5).all()
    storyline_lines = []
    for s in storylines:
        beats = list(s.key_beats or [])
        last_beat = ""
        if beats:
            beat = beats[-1]
            if isinstance(beat, dict):
                last_beat = beat.get("beat") or beat.get("milestone") or ""
            else:
                last_beat = str(beat)
        desc = _truncate(last_beat or s.core_conflict or s.description, 90)
        storyline_lines.append(f"{s.name}（{s.status}）：{desc}")

    bridge_lines = []
    if previous_chapter_number > 0:
        bridge_lines.append(
            f"本章必须承接第{previous_chapter_number}章结尾，不得跳过报信、反应、转场等因果链。"
        )
    if outline_node and outline_node.power_milestone:
        bridge_lines.append(f"本章实力目标：{outline_node.power_milestone}")
    if outline_node and (outline_node.foreshadows_resolved or outline_node.foreshadows_laid):
        bridge_lines.append("伏笔必须有前因后果；不得凭空写角色已经知道未在前文出现的信息。")

    # ── 全局伏笔管理表：优先传 open 状态伏笔 ────────────────────────────
    global_foreshadows = db.query(Foreshadow).filter(
        Foreshadow.project_id == project_id,
        Foreshadow.status == "open",
    ).order_by(Foreshadow.priority.desc(), Foreshadow.created_at).limit(12).all()
    foreshadow_lines = []
    for f in global_foreshadows:
        parts = [f.code or "F-?", f.title]
        if f.laid_chapter_number:
            parts.append(f"(第{f.laid_chapter_number}章埋)")
        if f.planned_resolve_chapter:
            planned_label = "铺垫" if getattr(f, "planned_action", "resolve") == "develop" else "回收"
            parts.append(f"→预计第{f.planned_resolve_chapter}章{planned_label}")
        if f.description:
            parts.append(f"：{_truncate(f.description, 60)}")
        foreshadow_lines.append("、".join(parts[:3]) + ("".join(parts[3:]) if len(parts) > 3 else ""))

    ban_lines = [
        "人物境界、位置、状态不得倒退或跳变，除非本章明确写出代价、原因和过渡。",
        "不得让角色掌握前文未获得的情报；新情报必须通过看见、听见、推理或前文伏笔获得。",
        "不得无提示跳过上一章钩子的直接反应。"
    ]

    sections = [
        f"截至第{previous_chapter_number}章事实表（用于生成第{current_chapter_number}章）：",
        "人物状态：" + ("；".join(char_lines) if char_lines else "无"),
        "力量体系：" + ("；".join(power_lines) if power_lines else "无"),
        "最近章节：" + ("；".join(recent_lines) if recent_lines else "无"),
        "记忆/伏笔：" + ("；".join(memory_lines) if memory_lines else "无"),
        "故事线进度：" + ("；".join(storyline_lines) if storyline_lines else "无"),
        "未解决承接点：" + ("；".join(bridge_lines) if bridge_lines else "无"),
        "禁止事项：" + "；".join(ban_lines),
    ]
    if foreshadow_lines:
        sections.insert(5, "⚠️未回收伏笔（必须可回收或持续铺垫，不得矛盾违背）：\n" +
                         "\n".join(f"  · {l}" for l in foreshadow_lines))
    return "\n".join(sections)


def _fmt_index_item(item) -> str:
    if isinstance(item, dict):
        return (
            item.get("description")
            or item.get("event")
            or item.get("name")
            or item.get("note")
            or json.dumps(item, ensure_ascii=False)
        )
    return str(item)


def _build_chapter_index_context(db: Session, project_id: str, chapter: Chapter) -> str:
    """最近章节索引 + 未回收伏笔，作为连续生成的主干导航。"""
    recent_indexes = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_number < chapter.sort_order + 1,
    ).order_by(ChapterIndex.chapter_number.desc()).limit(5).all()

    recent_lines = []
    for idx in reversed(recent_indexes):
        events = "；".join(_fmt_index_item(e) for e in (idx.core_events or [])[:3])
        hook = idx.ending_hook or ""
        notes = "；".join(_fmt_index_item(n) for n in (idx.continuity_notes or [])[:3])
        parts = [f"第{idx.chapter_number}章"]
        if idx.story_day:
            parts.append(f"故事日={idx.story_day}")
        if events:
            parts.append(f"核心事件={events}")
        if hook:
            parts.append(f"章末钩子={hook}")
        if notes:
            parts.append(f"连续性风险={notes}")
        recent_lines.append("；".join(parts))

    all_indexes = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_number < chapter.sort_order + 1,
    ).order_by(ChapterIndex.chapter_number).all()
    resolved_descriptions = {
        _fmt_index_item(item)
        for idx in all_indexes
        for item in (idx.actual_foreshadows_resolved or [])
        if _fmt_index_item(item)
    }
    open_foreshadows = []
    for idx in all_indexes:
        for item in (idx.actual_foreshadows_laid or []):
            desc = _fmt_index_item(item)
            status = item.get("status") if isinstance(item, dict) else ""
            if not desc or desc in resolved_descriptions or status == "resolved":
                continue
            open_foreshadows.append(f"第{idx.chapter_number}章：{desc}")

    sections = []
    if recent_lines:
        sections.append("最近章节索引：\n" + "\n".join(recent_lines))
    if open_foreshadows:
        sections.append("全量未回收伏笔：\n" + "\n".join(open_foreshadows[-12:]))
    return "\n\n".join(sections)


class QualityCheckRequest(BaseModel):
    chapter_id: str
    check_types: List[str] = ["plot", "character", "setting_consistency", "pacing", "hooks", "outline_alignment"]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SuggestRequest(BaseModel):
    chapter_id: str
    prompt: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChapterCoherenceCheckRequest(BaseModel):
    chapter_ids: List[str]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SaveChapterCoherenceReportRequest(BaseModel):
    name: Optional[str] = None
    model_profile: Literal["local", "gemini"] = "local"
    selected_chapter_ids: List[str]
    result: dict


# ── 质检 ──────────────────────────────────────────────
@router.post("/quality-check")
async def quality_check(
    project_id: str,
    req: QualityCheckRequest,
    db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    large_context = req.model_profile == "gemini"

    memory_query = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id
    ).order_by(MemoryChunk.chapter_number)
    memories = memory_query.limit(200 if large_context else 50).all()

    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()

    # ── 人物状态快照 ──────────────────────────────────────
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    def _skill_names(known_skills) -> str:
        if not known_skills:
            return "无"
        names = []
        for sk in known_skills[:5]:
            if isinstance(sk, dict):
                names.append(sk.get("skill_name", ""))
            else:
                names.append(str(sk))
        return "、".join(n for n in names if n) or "无"

    character_states = [
        f"{c.name}：境界={c.current_realm or '未知'}，"
        f"位置={c.current_location or '未知'}，"
        f"状态={c.current_status or 'alive'}，"
        f"已知技能=[{_skill_names(c.known_skills)}]"
        for c in characters
    ]

    # ── 活跃故事线 ────────────────────────────────────────
    active_storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["active", "climax"])
    ).all()
    storylines_context = [
        f"{s.name}（{s.line_type}，{s.status}）：{s.core_conflict or s.description or ''}"
        for s in active_storylines
    ]

    # ── 境界体系摘要 ──────────────────────────────────────
    power_systems = db.query(PowerSystem).filter(
        PowerSystem.project_id == project_id
    ).all()
    power_systems_summary = []
    for ps in power_systems:
        if large_context:
            levels = []
            for level in (ps.levels or []):
                if isinstance(level, dict):
                    rank = level.get("rank")
                    name = level.get("name") or ""
                    requirement = level.get("requirement") or level.get("description") or ""
                    levels.append(f"{rank}.{name}({requirement})" if rank else f"{name}({requirement})")
                else:
                    levels.append(str(level))
            rules = ps.special_rules or ps.breakthrough_condition or ps.description or ""
            power_systems_summary.append(
                f"{ps.name}：等级={' > '.join(levels) or '未知'}；"
                f"主角当前={ps.protagonist_current_rank or '未知'}；规则={rules}"
            )
        else:
            power_systems_summary.append(
                f"{ps.name}：最高境界={ps.levels[-1].get('name','') if ps.levels else '未知'}，主角当前={ps.protagonist_current_rank or '未知'}"
            )

    # ── 大纲上下文（本章节点）────────────────────────────
    outline_context = ""
    if chapter.outline_node_id:
        node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()
        if node:
            parts = []
            if node.summary:
                parts.append(f"本章摘要：{node.summary}")
            if large_context and node.hook:
                parts.append(f"开篇钩子：{node.hook}")
            if large_context and node.conflict:
                parts.append(f"核心冲突：{node.conflict}")
            if large_context and node.highlight:
                parts.append(f"章末方向：{node.highlight}")
            if node.power_milestone:
                parts.append(f"实力里程碑：{node.power_milestone}")
            if node.emotional_tone:
                parts.append(f"情感基调：{node.emotional_tone}")
            if node.foreshadows_laid:
                foreshadow_descs = [
                    f.get("description", "") if isinstance(f, dict) else str(f)
                    for f in node.foreshadows_laid[:3]
                ]
                parts.append(f"本章埋下伏笔：{'；'.join(foreshadow_descs)}")
            outline_context = "；".join(parts)

    continuity_context = _build_continuity_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=node if chapter.outline_node_id else None,
    )
    chapter_index_context = _build_chapter_index_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
    )

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.quality_check(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        memories=[m.content for m in memories],
        settings_summary=[f"{s.title}: {s.content or ''}" for s in settings],
        check_types=req.check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_context,
        chapter_index_context=chapter_index_context,
    )

    # 缓存质检结果
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    from sqlalchemy.sql import func
    chapter.quality_checked_at = func.now()
    db.commit()

    return result


@router.post("/chapter-coherence-check")
async def chapter_coherence_check(
    project_id: str,
    req: ChapterCoherenceCheckRequest,
    db: Session = Depends(get_db),
):
    if len(req.chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节进行连贯性检测")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    large_context = req.model_profile == "gemini"

    chapters = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.id.in_(req.chapter_ids),
    ).all()
    if len(chapters) != len(set(req.chapter_ids)):
        raise HTTPException(400, "存在无效章节ID，或章节不属于当前小说")

    chapters = sorted(chapters, key=lambda c: c.sort_order)
    selected_numbers = [c.sort_order + 1 for c in chapters]
    min_selected = min(selected_numbers)
    max_selected = max(selected_numbers)

    project_context_parts = []
    if project.premise:
        project_context_parts.append(f"作品基本面：{_truncate(project.premise, 4000 if large_context else 600)}")

    settings = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    if settings:
        setting_limit = 60 if large_context else 8
        setting_len = 1200 if large_context else 160
        project_context_parts.append(
            "世界观设定：\n" + "\n".join(
                f"- {s.title}: {_truncate(s.content, setting_len)}"
                for s in settings[:setting_limit]
            )
        )

    characters = db.query(Character).filter(Character.project_id == project_id).all()
    if characters:
        char_limit = 80 if large_context else 12
        project_context_parts.append(
            "人物状态：\n" + "\n".join(
                f"- {c.name}: 境界={c.current_realm or '未知'}；位置={c.current_location or '未知'}；"
                f"状态={c.current_status or 'alive'}；动机={_truncate(c.motivation, 180 if large_context else 50)}"
                for c in characters[:char_limit]
            )
        )

    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"]),
    ).order_by(StoryLine.sort_order).all()
    if storylines:
        storyline_limit = 50 if large_context else 8
        project_context_parts.append(
            "故事线进度：\n" + "\n".join(
                f"- {s.name}（{s.status}）：{_truncate(s.core_conflict or s.description, 500 if large_context else 100)}；"
                f"关键节拍={json.dumps(s.key_beats or [], ensure_ascii=False)[:1600 if large_context else 260]}"
                for s in storylines[:storyline_limit]
            )
        )

    indexes = db.query(ChapterIndex).filter(
        ChapterIndex.project_id == project_id,
        ChapterIndex.chapter_number <= max_selected,
    ).order_by(ChapterIndex.chapter_number).all()
    if indexes:
        index_window = [
            idx for idx in indexes
            if large_context or idx.chapter_number >= max(1, min_selected - 5)
        ]
        project_context_parts.append(
            "章节索引与伏笔：\n" + "\n".join(
                f"- 第{idx.chapter_number}章：核心事件={json.dumps(idx.core_events or [], ensure_ascii=False)[:700]}; "
                f"章末钩子={idx.ending_hook or ''}; "
                f"未回收/已回收伏笔={json.dumps(idx.actual_foreshadows_laid or [], ensure_ascii=False)[:700]} / "
                f"{json.dumps(idx.actual_foreshadows_resolved or [], ensure_ascii=False)[:700]}"
                for idx in index_window
            )
        )

    memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id,
        MemoryChunk.chapter_number <= max_selected,
    ).order_by(MemoryChunk.chapter_number.desc()).limit(100 if large_context else 20).all()
    if memories:
        project_context_parts.append(
            "记忆库：\n" + "\n".join(
                f"- 第{m.chapter_number or '?'}章 {m.title or m.memory_type}: {_truncate(m.content, 700 if large_context else 120)}"
                for m in memories
            )
        )

    project_context = "\n\n".join(project_context_parts)
    payload = [
        {
            "id": str(c.id),
            "sort_order": c.sort_order,
            "title": c.title,
            "content": c.content or "",
        }
        for c in chapters
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )
    result = await svc.chapter_coherence_check(
        project_title=project.title,
        chapters=payload,
        project_context=project_context,
    )
    result["selected_chapter_count"] = len(payload)
    result["selected_chapter_ids"] = [p["id"] for p in payload]
    return result


@router.post("/chapter-coherence-reports")
def save_chapter_coherence_report(
    project_id: str,
    req: SaveChapterCoherenceReportRequest,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if len(req.selected_chapter_ids) < 2:
        raise HTTPException(400, "至少选择2个章节才能保存检测记录")

    chapter_count = len(req.selected_chapter_ids)
    report = ChapterCoherenceReport(
        project_id=project_id,
        name=(req.name or f"连贯性检测（{chapter_count}章）").strip()[:200],
        model_profile=req.model_profile,
        selected_chapter_ids=req.selected_chapter_ids,
        result=req.result or {},
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": str(report.id),
        "name": report.name,
        "model_profile": report.model_profile,
        "selected_chapter_ids": report.selected_chapter_ids,
        "result": report.result,
        "created_at": report.created_at,
    }


@router.get("/chapter-coherence-reports")
def list_chapter_coherence_reports(
    project_id: str,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    safe_limit = 1 if limit < 1 else (100 if limit > 100 else limit)
    reports = (
        db.query(ChapterCoherenceReport)
        .filter(ChapterCoherenceReport.project_id == project_id)
        .order_by(ChapterCoherenceReport.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "model_profile": r.model_profile,
            "selected_chapter_ids": r.selected_chapter_ids or [],
            "result": r.result or {},
            "created_at": r.created_at,
        }
        for r in reports
    ]


# ── AI 建议（流式）─────────────────────────────────────
@router.post("/suggest/stream")
async def suggest_stream(
    project_id: str,
    req: SuggestRequest,
    db: Session = Depends(get_db)
):
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        async for chunk in svc.suggest_stream(
            chapter_content=chapter.content,
            user_prompt=req.prompt
        ):
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── 记忆库提取 ────────────────────────────────────────
@router.post("/extract-memory", response_model=List[MemoryChunkOut])
async def extract_memory(
    project_id: str,
    chapter_id: str,
    model_profile: Literal["local", "gemini"] = "local",
    llm_provider_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    svc = AIService(
        "gemini" if model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=llm_provider_id,
    )
    extracted = await svc.extract_memory(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        chapter_number=chapter.sort_order + 1,
    )

    results = []
    for item in extracted:
        chunk = MemoryChunk(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter.sort_order + 1,
            **item
        )
        db.add(chunk)
        results.append(chunk)
    db.commit()
    for r in results:
        db.refresh(r)
    return results


# ── AI 辅助写作（流式起笔/续写）──────────────────────
class DraftAssistRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    """作者补充说明：风格、禁忌、情节走向等，会并入提示词"""
    user_prompt: Optional[str] = None
    """为 True 时按「整章重写」生成，不把长正文当作续写衔接"""
    replace_existing: bool = False


@router.post("/draft-assist/stream")
async def draft_assist_stream(
    project_id: str,
    req: DraftAssistRequest,
    db: Session = Depends(get_db)
):
    """
    根据章节大纲计划 + 世界观 + 人物 + 记忆库 + 前章结尾，
    流式生成本章起笔或续写建议。
    像一位有 30 年经验的作家：把设定、人物弧、伏笔自然织入正文。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    large_context = req.model_profile == "gemini"

    # ── 大纲节点（可选）──────────────────────────────
    outline_node = None
    if chapter.outline_node_id:
        outline_node = db.query(OutlineNode).filter(
            OutlineNode.id == chapter.outline_node_id
        ).first()

    # ── 世界观设定 ────────────────────────────────────
    settings = db.query(WorldSetting).filter(
        WorldSetting.project_id == project_id
    ).all()
    if large_context:
        world_summary = "\n".join(
            f"- [{s.category.name if s.category else 'setting'}] {s.title}: {_truncate(s.content, 2400)}"
            for s in settings
        )
    else:
        world_summary = " | ".join(
            f"{s.title}: {(s.content or '')[:70]}" for s in settings[:5]
        )

    # ── 人物（含新增状态字段）────────────────────────────
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    # 如果大纲节点标注了出场人物，优先展示这些人物
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

    # 严格限定模式：大纲有人物清单时，只传清单内人物（第二道锁）
    # 旧数据无 involved_ids 时退回兼容模式（最多 6 人）
    chapter_manifest_names: list[str] = []
    if involved_ids:
        priority = [c for c in characters if str(c.id) in involved_ids]
        display_chars = priority          # 不补全非清单人物
        chapter_manifest_names = [c.name for c in priority]
    else:
        display_chars = characters if large_context else characters[:6]    # 兼容旧大纲，无清单约束

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
            parts.append(f"动机:{_truncate(c.motivation, 180 if large_context else 30)}")
        if large_context and c.values:
            parts.append(f"价值观:{_truncate(c.values, 180)}")
        if large_context and c.fear:
            parts.append(f"恐惧:{_truncate(c.fear, 140)}")
        if large_context and c.secrets:
            parts.append(f"秘密:{_truncate(c.secrets, 180)}")
        if large_context and c.known_skills:
            parts.append(f"技能明细:{json.dumps(c.known_skills, ensure_ascii=False)[:1200]}")
        if large_context and c.owned_items:
            parts.append(f"持有物:{json.dumps(c.owned_items, ensure_ascii=False)[:1200]}")
        char_lines.append("".join(parts))

    char_summary = "\n".join(char_lines) if large_context else " | ".join(char_lines)

    # ── 活跃故事线（draft 用）────────────────────────────
    active_statuses = ["planned", "active", "climax"] if large_context else ["active", "climax"]
    active_storylines_draft = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(active_statuses)
    ).order_by(StoryLine.sort_order).all()
    if large_context:
        storyline_summary = "\n".join(
            f"- {s.name}（{s.line_type}/{s.status}）："
            f"{_truncate(s.core_conflict or s.description, 500)}；"
            f"关键节拍={json.dumps(s.key_beats or [], ensure_ascii=False)[:1600]}"
            for s in active_storylines_draft
        )
    else:
        storyline_summary = "；".join(
            f"{s.name}（{s.line_type}）：{(s.core_conflict or s.description or '')[:60]}"
            for s in active_storylines_draft[:4]
        )

    # ── 记忆库（最近事件）────────────────────────────
    memories = db.query(MemoryChunk).filter(
        MemoryChunk.project_id == project_id
    ).order_by(MemoryChunk.chapter_number.desc()).limit(80 if large_context else 12).all()
    if large_context:
        memory_summary = "\n".join(
            f"- 第{m.chapter_number or '?'}章 {m.title or m.memory_type}: {_truncate(m.content, 600)}"
            for m in memories
        )
    else:
        memory_summary = " | ".join(
            f"{m.title or m.memory_type}: {m.content[:60]}" for m in memories
        )

    # ── 上一章结尾（衔接用）──────────────────────────
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()

    prev_tail = ""
    if prev_chapter and prev_chapter.content:
        clean = _plain_text(prev_chapter.content)
        prev_limit = 3000 if large_context else 400
        prev_tail = clean[-prev_limit:] if len(clean) > prev_limit else clean

    # ── 当前章节正文（strip HTML）────────────────────
    existing_content = _plain_text(chapter.content)
    continuity_context = _build_continuity_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=outline_node,
    )
    chapter_index_context = _build_chapter_index_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
    )

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        try:
            # ── 伏笔：优先读结构化字段，兼容旧 extra.foreshadow ──
            def _fmt_foreshadows(node) -> str:
                if not node:
                    return ""
                laid = node.foreshadows_laid or []
                resolved = node.foreshadows_resolved or []
                parts = []
                if laid:
                    descs = [
                        (f.get("description", "") if isinstance(f, dict) else str(f))
                        for f in laid[:3]
                    ]
                    parts.append("埋[" + "；".join(d for d in descs if d) + "]")
                if resolved:
                    descs = [
                        (f.get("description", "") if isinstance(f, dict) else str(f))
                        for f in resolved[:3]
                    ]
                    parts.append("收[" + "；".join(d for d in descs if d) + "]")
                # 兼容旧数据：extra.foreshadow 文本
                if not parts:
                    legacy = (node.extra or {}).get("foreshadow", "")
                    if legacy:
                        return legacy
                return "  ".join(parts)

            # ── story_day（新字段，存于 extra）───────────────────
            story_day = ""
            if outline_node:
                story_day = (outline_node.extra or {}).get("story_day", "")

            async for chunk in svc.draft_assist_stream(
                chapter_title=chapter.title,
                outline_hook=outline_node.hook or "" if outline_node else "",
                outline_summary=outline_node.summary or "" if outline_node else "",
                outline_conflict=outline_node.conflict or "" if outline_node else "",
                outline_highlight=outline_node.highlight or "" if outline_node else "",
                outline_foreshadow=_fmt_foreshadows(outline_node),
                outline_power_milestone=outline_node.power_milestone or "" if outline_node else "",
                outline_emotional_tone=outline_node.emotional_tone or "" if outline_node else "",
                story_day=story_day,
                chapter_manifest=chapter_manifest_names,
                prev_chapter_tail=prev_tail,
                world_summary=world_summary,
                character_summary=char_summary,
                storyline_summary=storyline_summary,
                memory_summary=memory_summary,
                existing_content=existing_content,
                premise=project.premise or "",
                user_prompt=req.user_prompt or "",
                replace_existing=req.replace_existing,
                continuity_context=continuity_context,
                chapter_index_context=chapter_index_context,
            ):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 章节复盘（写完后批量更新人物状态/故事线进展）────────
class CharacterUpdate(BaseModel):
    character_id: str
    current_realm: Optional[str] = None
    realm_rank: Optional[int] = None
    current_location: Optional[str] = None
    current_status: Optional[str] = None
    add_skill: Optional[dict] = None      # {"skill_id": "...", "skill_name": "...", "mastery": "初学"}
    add_item: Optional[dict] = None       # {"item_id": "...", "item_name": "...", "acquired_chapter": 5}
    remove_item_id: Optional[str] = None  # 失去道具时传 item_id

class StoryLineUpdate(BaseModel):
    storyline_id: Optional[str] = None
    storyline_name: Optional[str] = None
    status: Optional[str] = None          # planned/active/climax/resolved/dropped
    append_beat: Optional[str] = None     # 追加到 key_beats 的新节点描述

class MemoryUpdate(BaseModel):
    memory_type: Literal["event", "character_state", "foreshadow", "setting", "conflict"] = "event"
    title: Optional[str] = None
    content: str
    tags: List[str] = []

class ChapterIndexPayload(BaseModel):
    story_day: Optional[str] = None
    core_events: List[dict | str] = []
    first_appearances: List[dict] = []
    actual_foreshadows_laid: List[dict] = []
    actual_foreshadows_resolved: List[dict] = []
    ending_hook: Optional[str] = None
    hook_strength: int = 1
    continuity_notes: List[dict | str] = []

class ChapterDebriefRequest(BaseModel):
    chapter_id: str
    character_updates: List[CharacterUpdate] = []
    storyline_updates: List[StoryLineUpdate] = []
    memory_updates: List[MemoryUpdate] = []
    chapter_index: Optional[ChapterIndexPayload] = None
    notes: Optional[str] = None           # 作者备注，存到 chapter

@router.post("/chapter-debrief")
def chapter_debrief(
    project_id: str,
    req: ChapterDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    章节写完后的「复盘提交」：批量更新人物状态、故事线进展。
    前端在写作页右侧面板提交，避免「写了文章但数据库状态停留在第1章」的空架子问题。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    updated_chars: List[str] = []
    updated_storylines: List[str] = []
    added_memories: List[str] = []
    chapter_index_saved = False
    chapter_index_error: Optional[str] = None
    synced_foreshadows = {"created": 0, "updated": 0, "resolved": 0}

    # ── 更新人物状态 ──────────────────────────────────
    for cu in req.character_updates:
        try:
            _ = UUID(str(cu.character_id))
        except Exception:
            # 非法 ID 直接跳过，避免整次复盘 500
            continue

        char = db.query(Character).filter(
            Character.id == cu.character_id,
            Character.project_id == project_id,
        ).first()
        if not char:
            continue

        if cu.current_realm is not None:
            char.current_realm = cu.current_realm.strip()[:100]
        if cu.realm_rank is not None:
            char.realm_rank = cu.realm_rank
        if cu.current_location is not None:
            char.current_location = cu.current_location.strip()[:200]
        if cu.current_status is not None:
            normalized_status = _normalize_character_status(cu.current_status)
            if normalized_status:
                char.current_status = normalized_status

        # 追加新技能
        if cu.add_skill:
            skills = list(char.known_skills or [])
            # 防止重复（相同 skill_id 则更新 mastery）
            existing_ids = {
                s.get("skill_id") for s in skills if isinstance(s, dict)
            }
            if cu.add_skill.get("skill_id") in existing_ids:
                skills = [
                    {**s, "mastery": cu.add_skill.get("mastery", s.get("mastery"))}
                    if isinstance(s, dict) and s.get("skill_id") == cu.add_skill.get("skill_id")
                    else s
                    for s in skills
                ]
            else:
                skills.append(cu.add_skill)
            char.known_skills = skills

        # 追加新道具
        if cu.add_item:
            items = list(char.owned_items or [])
            existing_item_ids = {
                i.get("item_id") for i in items if isinstance(i, dict)
            }
            if cu.add_item.get("item_id") not in existing_item_ids:
                items.append(cu.add_item)
            char.owned_items = items

        # 移除道具
        if cu.remove_item_id:
            char.owned_items = [
                i for i in (char.owned_items or [])
                if not (isinstance(i, dict) and i.get("item_id") == cu.remove_item_id)
            ]

        updated_chars.append(char.name)

    # ── 更新故事线 ────────────────────────────────────
    for su in req.storyline_updates:
        storyline_uuid = None
        if su.storyline_id:
            try:
                storyline_uuid = UUID(str(su.storyline_id))
            except Exception:
                storyline_uuid = None

        if storyline_uuid:
            sl = db.query(StoryLine).filter(
                StoryLine.id == storyline_uuid,
                StoryLine.project_id == project_id,
            ).first()
        elif su.storyline_name:
            # AI 偶发返回 name/key 而不是 UUID；按名称兜底匹配
            sl = db.query(StoryLine).filter(
                StoryLine.name == su.storyline_name,
                StoryLine.project_id == project_id,
            ).first()
        else:
            continue

        if not sl:
            continue

        if su.status is not None:
            normalized_storyline_status = _normalize_storyline_status(su.status)
            if normalized_storyline_status:
                sl.status = normalized_storyline_status
        if su.append_beat:
            beats = list(sl.key_beats or [])
            beats.append({
                "chapter": chapter.sort_order + 1,
                "chapter_title": chapter.title,
                "beat": su.append_beat,
            })
            sl.key_beats = beats

        updated_storylines.append(sl.name)

    # ── 写入章节记忆/伏笔/信息来源 ─────────────────────
    for mu in req.memory_updates:
        content = (mu.content or "").strip()
        if not content:
            continue
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=chapter.sort_order + 1,
            memory_type=mu.memory_type,
            title=(mu.title or mu.memory_type).strip()[:200],
            content=content,
            tags=mu.tags[:8],
        )
        db.add(memory)
        added_memories.append(memory.title or memory.memory_type)

    # ── 写入/更新章节速查索引 ─────────────────────────
    if req.chapter_index:
        try:
            with db.begin_nested():
                hook_strength = max(1, min(5, req.chapter_index.hook_strength or 1))
                index = db.query(ChapterIndex).filter(
                    ChapterIndex.project_id == project_id,
                    ChapterIndex.chapter_id == req.chapter_id,
                ).first()
                data = req.chapter_index.model_dump()
                data["hook_strength"] = hook_strength
                data["chapter_number"] = chapter.sort_order + 1
                if index:
                    for field, value in data.items():
                        setattr(index, field, value)
                else:
                    index = ChapterIndex(
                        project_id=project_id,
                        chapter_id=req.chapter_id,
                        **data,
                    )
                    db.add(index)
                chapter_index_saved = True
                synced_foreshadows = _sync_chapter_index_foreshadows(
                    db,
                    project_id,
                    chapter,
                    req.chapter_index,
                )
        except SQLAlchemyError as exc:
            chapter_index_error = exc.__class__.__name__

    # ── 保存作者备注到章节 ────────────────────────────
    if req.notes:
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=chapter.sort_order + 1,
            memory_type="event",
            title="章节复盘备注",
            content=req.notes.strip(),
            tags=["复盘备注"],
        )
        db.add(memory)
        added_memories.append(memory.title)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(400, f"章节复盘提交失败：{exc.__class__.__name__}")

    return {
        "ok": True,
        "updated_characters": updated_chars,
        "updated_storylines": updated_storylines,
        "added_memories": added_memories,
        "chapter_index_saved": chapter_index_saved,
        "chapter_index_error": chapter_index_error,
        "synced_foreshadows": synced_foreshadows,
        "message": (
            f"已更新 {len(updated_chars)} 个人物状态、{len(updated_storylines)} 条故事线、"
            f"{len(added_memories)} 条记忆、章节索引={'已写入' if chapter_index_saved else '未更新'}、"
            f"伏笔管理新增{synced_foreshadows['created']}条/更新{synced_foreshadows['updated']}条/"
            f"回收{synced_foreshadows['resolved']}条"
        ),
    }


# ── 自动复盘提取（AI 读章节 → 建议人物/故事线更新）────────
class AutoDebriefRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None

@router.post("/auto-debrief")
async def auto_debrief(
    project_id: str,
    req: AutoDebriefRequest,
    db: Session = Depends(get_db),
):
    """
    AI 读取章节正文，对照当前人物状态和故事线，
    提取本章发生的状态变化建议。结果仅供前端预填，
    不直接写库——需用户确认后调用 /chapter-debrief 提交。
    """
    chapter = db.query(Chapter).filter(
        Chapter.id == req.chapter_id, Chapter.project_id == project_id
    ).first()
    if not chapter:
        raise HTTPException(404, "Chapter not found")

    if not (chapter.content or "").strip():
        return {
            "character_updates": [],
            "storyline_updates": [],
            "summary": "章节内容为空，无法分析",
        }

    # 构建人物状态快照
    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).all()
    character_states = [
        {
            "id": str(c.id),
            "name": c.name,
            "current_realm": c.current_realm or "",
            "current_location": c.current_location or "",
            "current_status": c.current_status or "alive",
        }
        for c in characters
    ]

    # 构建故事线快照（只取活跃/规划中的）
    storylines = db.query(StoryLine).filter(
        StoryLine.project_id == project_id,
        StoryLine.status.in_(["planned", "active", "climax"])
    ).all()
    storylines_data = [
        {
            "id": str(s.id),
            "name": s.name,
            "line_type": s.line_type,
            "status": s.status,
            "core_conflict": s.core_conflict or s.description or "",
        }
        for s in storylines
    ]

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    # strip HTML
    import re as _re
    plain_content = _re.sub(r"<[^>]+>", "", chapter.content or "")

    result = await svc.auto_extract_debrief(
        chapter_content=plain_content,
        chapter_title=chapter.title,
        chapter_number=chapter.sort_order + 1,
        character_states=character_states,
        storylines=storylines_data,
    )
    return result


# ── 记忆库查询 ────────────────────────────────────────
@router.get("/memory", response_model=List[MemoryChunkOut])
def list_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = db.query(MemoryChunk).filter(MemoryChunk.project_id == project_id)
    if memory_type:
        q = q.filter(MemoryChunk.memory_type == memory_type)
    return q.order_by(MemoryChunk.chapter_number).all()
