from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime, timezone
from uuid import UUID, uuid4
import json
import re
import hashlib

from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block

from app.database import get_db, SessionLocal
from app.services.embedding_service import embed_chunk_async
from app.models import (
    Chapter,
    ChapterVersion,
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
    Faction,
    Item,
    Skill,
    ChapterDebriefCache,
    AiChatMessage,
    QualityDebt,
)
from app.schemas import MemoryChunkCreate, MemoryChunkOut
from app.services.ai_service import AIService
from app.utils.chapter_numbering import display_chapter_number

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])

_ALLOWED_CHARACTER_STATUS = {"alive", "dead", "missing", "sealed", "transformed"}
_ALLOWED_STORYLINE_STATUS = {"planned", "active", "climax", "resolved", "dropped"}
_QUALITY_DEBT_TYPES = {
    "character",
    "character_state",
    "character_location",
    "continuity",
    "continuity_gap",
    "foreshadow",
    "hook_continuity",
    "hooks",
    "outline_alignment",
    "plot",
    "setting",
    "setting_consistency",
    "power_system",
}
_QUALITY_DEBT_SEVERITIES = {"critical", "high", "medium"}


def _plain_text(html: str | None) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def _truncate(text: str | None, limit: int) -> str:
    clean = (text or "").strip()
    return clean[:limit]


def _extract_patch_text(value) -> str:
    if isinstance(value, dict):
        for key in ("replacement", "suggestion", "suggested_fix", "patch", "description"):
            text = value.get(key)
            if isinstance(text, str) and text.strip():
                return text.strip()
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        return value.strip()
    return ""


def _quality_debt_fingerprint(project_id: str, chapter_id: str, issue_type: str, summary: str) -> str:
    raw = f"{project_id}|{chapter_id}|{issue_type}|{summary.strip()[:240]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_quality_debt_items(report: dict | None) -> list[dict]:
    if not isinstance(report, dict):
        return []

    candidates: list[dict] = []
    for issue in report.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issue_type = str(issue.get("type") or "plot").strip().lower()
        severity = str(issue.get("severity") or "medium").strip().lower()
        summary = str(issue.get("description") or issue.get("summary") or "").strip()
        suggested_fix = (
            _extract_patch_text(issue.get("suggested_patch"))
            or _extract_patch_text(issue.get("suggestion"))
            or _extract_patch_text(issue.get("suggested_fix"))
        )
        candidates.append({
            "issue_type": issue_type,
            "severity": severity,
            "summary": summary,
            "suggested_fix": suggested_fix,
        })

    for suggestion in report.get("suggestions") or []:
        if not isinstance(suggestion, dict):
            continue
        issue_type = str(suggestion.get("type") or "plot").strip().lower()
        severity = str(suggestion.get("severity") or "medium").strip().lower()
        summary = str(suggestion.get("description") or suggestion.get("summary") or suggestion.get("suggestion") or "").strip()
        candidates.append({
            "issue_type": issue_type,
            "severity": severity,
            "summary": summary,
            "suggested_fix": _extract_patch_text(suggestion.get("suggested_fix") or suggestion.get("suggestion")),
        })

    debts: list[dict] = []
    seen = set()
    for item in candidates:
        issue_type = item["issue_type"]
        severity = item["severity"]
        summary = item["summary"]
        if not summary:
            continue
        if severity not in _QUALITY_DEBT_SEVERITIES:
            continue
        if issue_type not in _QUALITY_DEBT_TYPES:
            continue
        dedupe_key = (issue_type, summary[:240])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        debts.append({
            **item,
            "severity": severity,
            "summary": _truncate(summary, 500),
            "suggested_fix": _truncate(item.get("suggested_fix") or "", 500),
        })
    return debts[:8]


def _sync_quality_debts(db: Session, project_id: str, chapter: Chapter, report: dict) -> list[QualityDebt]:
    synced: list[QualityDebt] = []
    for item in _extract_quality_debt_items(report):
        fingerprint = _quality_debt_fingerprint(
            project_id,
            str(chapter.id),
            item["issue_type"],
            item["summary"],
        )
        debt = db.query(QualityDebt).filter(
            QualityDebt.project_id == project_id,
            QualityDebt.fingerprint == fingerprint,
        ).first()
        if debt:
            debt.severity = item["severity"]
            debt.summary = item["summary"]
            debt.suggested_fix = item.get("suggested_fix") or debt.suggested_fix
        else:
            debt = QualityDebt(
                project_id=project_id,
                chapter_id=chapter.id,
                source_chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
                issue_type=item["issue_type"],
                severity=item["severity"],
                status="pending",
                summary=item["summary"],
                suggested_fix=item.get("suggested_fix") or None,
                fingerprint=fingerprint,
            )
            db.add(debt)
        synced.append(debt)
    return synced


def _build_quality_debt_context(debts: list[QualityDebt]) -> str:
    pending = [d for d in debts if getattr(d, "status", "pending") == "pending"]
    if not pending:
        return ""
    lines = ["【未解决质量债务 / 必须修正或规避】"]
    for debt in pending[:8]:
        line = (
            f"- 第{debt.source_chapter_number}章 "
            f"[{debt.severity}/{debt.issue_type}] {debt.summary}"
        )
        if debt.suggested_fix:
            line += f"；修正方向：{debt.suggested_fix}"
        lines.append(line)
    return "\n".join(lines)


def _pending_quality_debts_for_chapter(
    db: Session,
    project_id: str,
    chapter: Chapter,
    limit: int = 8,
) -> list[QualityDebt]:
    return (
        db.query(QualityDebt)
        .filter(
            QualityDebt.project_id == project_id,
            QualityDebt.status == "pending",
            QualityDebt.source_chapter_number <= display_chapter_number(chapter.title, chapter.sort_order),
        )
        .order_by(QualityDebt.source_chapter_number.desc(), QualityDebt.created_at.desc())
        .limit(limit)
        .all()
    )


def _strip_tail_meta_lines(text: str | None) -> str:
    """过滤章末结构化元信息，避免误当正文承接。"""
    lines = str(text or "").splitlines()
    cleaned: list[str] = []
    for line in lines:
        raw = line.strip()
        if not raw:
            cleaned.append(line)
            continue
        if re.match(r"^\*{0,2}\s*章末钩子强度", raw):
            continue
        if re.match(r"^\*{0,2}\s*伏笔埋设", raw):
            continue
        if re.match(r"^[-•]\s*F[-_ ]?\d{1,4}\s*[:：\-]", raw, flags=re.IGNORECASE):
            continue
        if re.search(r"\bch[_-]?\d+\s*(回收|铺垫)\b", raw, flags=re.IGNORECASE):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


_SETTING_CORE_LABELS = [
    ("core_concept", "一句话核心"),
    ("genre_position", "类型定位"),
    ("protagonist_drive", "主角驱动力"),
    ("core_conflict", "核心矛盾"),
    ("reader_hook", "追读钩子"),
    ("emotional_tone", "情感基调"),
    ("boundaries", "禁忌边界"),
    ("ending_direction", "结局倾向"),
]

_SETTING_FOCUS_LABELS = [
    ("summary", "核心摘要"),
    ("story_function", "故事作用"),
    ("conflict_seed", "冲突种子"),
    ("cost_or_risk", "代价/风险"),
    ("affected_people", "影响对象"),
    ("exception_or_loophole", "例外/漏洞"),
    ("visual_anchor", "画面锚点"),
]


def _read_setting_section(extra: dict, key: str) -> dict:
    section = extra.get(key)
    return section if isinstance(section, dict) else {}


def _format_world_setting_context(setting: WorldSetting, content_limit: int = 1200) -> str:
    extra = setting.extra if isinstance(setting.extra, dict) else {}
    category = extra.get("category") or (setting.category.name if setting.category else "setting")
    importance = extra.get("importance")
    stage = extra.get("stage")
    markers = [str(category)]
    if importance:
        markers.append(str(importance))
    if stage:
        markers.append(str(stage))

    lines = [f"[{'/'.join(markers)}] {setting.title}"]
    core = _read_setting_section(extra, "core")
    focus = _read_setting_section(extra, "focus")
    for key, label in _SETTING_CORE_LABELS:
        value = core.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")
    for key, label in _SETTING_FOCUS_LABELS:
        value = focus.get(key)
        if isinstance(value, str) and value.strip():
            lines.append(f"{label}：{value.strip()}")

    links = extra.get("links")
    if isinstance(links, dict):
        link_parts = []
        for key, label in [
            ("faction_names", "关联势力"),
            ("character_names", "关联人物"),
            ("storyline_names", "关联故事线"),
            ("power_system_names", "关联力量体系"),
        ]:
            values = links.get(key)
            if isinstance(values, list):
                names = "、".join(str(v) for v in values if v)
                if names:
                    link_parts.append(f"{label}={names}")
        if link_parts:
            lines.append("关联：" + "；".join(link_parts))

    content = _truncate(setting.content, content_limit)
    if content:
        lines.append(f"详细设定：{content}")
    return "\n".join(lines)


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
    chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
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
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()
    current_chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    previous_chapter_number = (
        display_chapter_number(prev_chapter.title, prev_chapter.sort_order)
        if prev_chapter
        else 0
    )

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
            recent_lines.append(
                f"第{display_chapter_number(c.title, c.sort_order)}章《{c.title}》：{_truncate(source, 160)}"
            )

    mem_rows_ctx = (
        db.query(MemoryChunk, Chapter)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(
            MemoryChunk.project_id == project_id,
            MemoryChunk.memory_type.in_(["foreshadow", "event", "character_state"]),
        )
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, -1).desc())
        .limit(8)
        .all()
    )
    memory_lines = []
    for m, ch in mem_rows_ctx:
        if not (m.content or "").strip():
            continue
        num = display_chapter_number(ch.title, ch.sort_order) if ch is not None else (m.chapter_number or "?")
        memory_lines.append(f"第{num}章 {m.title or m.memory_type}：{_truncate(m.content, 100)}")

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


def _string_ids(values) -> set[str]:
    return {str(value) for value in (values or []) if value}


def _json_ref_ids(values, key: str) -> set[str]:
    ids = set()
    for value in values or []:
        if isinstance(value, dict) and value.get(key):
            ids.add(str(value.get(key)))
    return ids


def _brief_text(value: str | None, limit: int = 90) -> str:
    return _truncate(value, limit).replace("\n", " ")


def _format_brief_line(name: str, attrs: list[str]) -> str:
    clean_attrs = [attr for attr in attrs if attr]
    return f"{name}（{'；'.join(clean_attrs)}）" if clean_attrs else name


def _build_writing_brief_context(
    db: Session,
    project_id: str,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
    large_context: bool = False,
) -> str:
    """Activate only the assets this chapter may consume: factions, items, and skills."""
    current_chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    involved_ids = _string_ids(outline_node.involved_character_ids if outline_node else [])
    key_item_ids = _string_ids(outline_node.key_item_ids if outline_node else [])
    key_skill_ids = _string_ids(outline_node.key_skill_ids if outline_node else [])

    characters = db.query(Character).filter(
        Character.project_id == project_id
    ).order_by(Character.role, Character.name).all()
    if involved_ids:
        active_characters = [c for c in characters if str(c.id) in involved_ids]
    else:
        active_characters = [
            c for c in characters
            if c.role in {"protagonist", "antagonist"}
        ][:6] or characters[:6]
    active_character_ids = {str(c.id) for c in active_characters}
    owned_item_ids = set().union(*[
        _json_ref_ids(c.owned_items, "item_id") for c in active_characters
    ]) if active_characters else set()
    known_skill_ids = set().union(*[
        _json_ref_ids(c.known_skills, "skill_id") for c in active_characters
    ]) if active_characters else set()
    faction_ids = {str(c.faction_id) for c in active_characters if c.faction_id}
    faction_names = {c.faction for c in active_characters if c.faction}

    items = db.query(Item).filter(
        Item.project_id == project_id
    ).order_by(Item.sort_order, Item.created_at).all()
    activated_items = []
    for item in items:
        item_id = str(item.id)
        owner_id = str(item.current_owner_id) if item.current_owner_id else ""
        first_seen = item.first_appearance_chapter or 0
        is_core_by_rarity = item.rarity in {"unique", "mythic", "legendary"} and (
            owner_id in active_character_ids
            or (first_seen and first_seen <= current_chapter_number)
        )
        if (
            item_id in key_item_ids
            or item_id in owned_item_ids
            or owner_id in active_character_ids
            or is_core_by_rarity
        ):
            activated_items.append(item)

    skills = db.query(Skill).filter(
        Skill.project_id == project_id
    ).order_by(Skill.sort_order, Skill.created_at).all()
    activated_skills = []
    for skill in skills:
        skill_id = str(skill.id)
        mastered_by = _string_ids(skill.mastered_by_character_ids)
        first_seen = skill.first_appearance_chapter or 0
        if (
            skill_id in key_skill_ids
            or skill_id in known_skill_ids
            or bool(mastered_by & active_character_ids)
            or (first_seen and first_seen <= current_chapter_number and skill.grade in {"divine", "supreme"})
        ):
            activated_skills.append(skill)

    factions = db.query(Faction).filter(
        Faction.project_id == project_id
    ).order_by(Faction.sort_order, Faction.created_at).all()
    activated_factions = [
        f for f in factions
        if str(f.id) in faction_ids or f.name in faction_names
    ]

    item_limit = 12 if large_context else 5
    skill_limit = 12 if large_context else 5
    faction_limit = 10 if large_context else 4
    sections = ["【本章写前 Brief / 激活资产】"]

    if activated_factions:
        faction_lines = []
        for faction in activated_factions[:faction_limit]:
            faction_lines.append(_format_brief_line(
                faction.name,
                [
                    f"立场={faction.alignment}" if faction.alignment else "",
                    f"对主角态度={faction.attitude_to_protagonist}" if faction.attitude_to_protagonist else "",
                    f"资源={_brief_text(faction.resources)}" if faction.resources else "",
                    f"目标={_brief_text(faction.goals)}" if faction.goals else "",
                ],
            ))
        sections.append("激活势力：" + "；".join(faction_lines))
        sections.append("势力消费方式：只把势力当作身份、资源、阻力或冲突来源；本章后若关系变化，章后复盘更新态度或故事线。")

    if activated_items:
        item_lines = []
        for item in activated_items[:item_limit]:
            item_lines.append(_format_brief_line(
                item.name,
                [
                    "/".join(part for part in [item.item_type, item.rarity] if part),
                    f"状态={item.status}" if item.status else "",
                    f"效果={_brief_text(item.effects)}" if item.effects else "",
                    f"限制={_brief_text(item.limitations)}" if item.limitations else "",
                    f"意义={_brief_text(item.story_significance)}" if item.story_significance else "",
                ],
            ))
        sections.append("激活道具/法宝：" + "；".join(item_lines))
        sections.append("道具消费方式：只使用已激活道具的已知能力；不得临场赋予新能力。若新增B级道具影响后文，章后入库并记录持有者、状态和限制。")

    if activated_skills:
        skill_lines = []
        for skill in activated_skills[:skill_limit]:
            skill_lines.append(_format_brief_line(
                skill.name,
                [
                    "/".join(part for part in [skill.skill_type, skill.grade] if part),
                    f"要求={_brief_text(skill.level_required)}" if skill.level_required else "",
                    f"效果={_brief_text(skill.effects)}" if skill.effects else "",
                    f"限制={_brief_text(skill.limitations)}" if skill.limitations else "",
                ],
            ))
        sections.append("激活功法/技能：" + "；".join(skill_lines))
        sections.append("技能消费方式：必须符合掌握者、境界、熟练度和代价；升级必须在正文写出原因，并在章后复盘更新人物技能。")

    if len(sections) == 1:
        return ""

    sections.append("C级临时资产：允许出现无名、一次性的丹药/符箓/小势力/普通招式；不得解决主冲突；若影响后续，章后复盘升格入库。")
    return "\n".join(sections)


def _build_chapter_index_context(db: Session, project_id: str, chapter: Chapter) -> str:
    """最近章节索引 + 未回收伏笔，作为连续生成的主干导航。"""
    recent_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order.desc())
        .limit(5)
        .all()
    )

    recent_lines = []
    for idx, ch in reversed(recent_rows):
        events = "；".join(_fmt_index_item(e) for e in (idx.core_events or [])[:3])
        hook = idx.ending_hook or ""
        notes = "；".join(_fmt_index_item(n) for n in (idx.continuity_notes or [])[:3])
        num = display_chapter_number(ch.title, ch.sort_order)
        parts = [f"第{num}章"]
        if idx.story_day:
            parts.append(f"故事日={idx.story_day}")
        if events:
            parts.append(f"核心事件={events}")
        if hook:
            parts.append(f"章末钩子={hook}")
        if notes:
            parts.append(f"连续性风险={notes}")
        recent_lines.append("；".join(parts))

    all_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    resolved_descriptions = {
        _fmt_index_item(item)
        for idx, _ch in all_rows
        for item in (idx.actual_foreshadows_resolved or [])
        if _fmt_index_item(item)
    }
    open_foreshadows = []
    for idx, ch in all_rows:
        num = display_chapter_number(ch.title, ch.sort_order)
        for item in (idx.actual_foreshadows_laid or []):
            desc = _fmt_index_item(item)
            status = item.get("status") if isinstance(item, dict) else ""
            if not desc or desc in resolved_descriptions or status == "resolved":
                continue
            open_foreshadows.append(f"第{num}章：{desc}")

    sections = []
    if recent_lines:
        sections.append("最近章节索引：\n" + "\n".join(recent_lines))
    if open_foreshadows:
        sections.append("全量未回收伏笔：\n" + "\n".join(open_foreshadows[-12:]))
    return "\n\n".join(sections)


def _build_plot_dossier_context(db: Session, project_id: str, chapter: Chapter, large_context: bool = False) -> str:
    """情节档案：章节索引主线 + 伏笔状态 + 当前活跃故事线。"""
    index_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    chapter_limit = 60 if large_context else 16
    index_lines = []
    for idx, ch in index_rows[-chapter_limit:]:
        num = display_chapter_number(ch.title, ch.sort_order)
        events = "；".join(_fmt_index_item(e) for e in (idx.core_events or [])[: (6 if large_context else 3)])
        hook = _truncate(idx.ending_hook, 220 if large_context else 120) if idx.ending_hook else ""
        notes = "；".join(_fmt_index_item(n) for n in (idx.continuity_notes or [])[: (5 if large_context else 2)])
        parts = [f"第{num}章《{ch.title}》"]
        if idx.story_day:
            parts.append(f"故事日={idx.story_day}")
        if events:
            parts.append(f"核心事件={events}")
        if hook:
            parts.append(f"章末钩子={hook}")
        if notes:
            parts.append(f"连续性备注={notes}")
        index_lines.append("；".join(parts))

    foreshadow_rows = (
        db.query(Foreshadow)
        .filter(Foreshadow.project_id == project_id)
        .order_by(Foreshadow.priority.desc(), Foreshadow.created_at.asc())
        .all()
    )
    foreshadow_limit = 30 if large_context else 12
    foreshadow_lines = []
    for f in foreshadow_rows[:foreshadow_limit]:
        parts = [f.code or "F-?", f.title, f"状态={f.status}"]
        if f.laid_chapter_number:
            parts.append(f"埋点=第{f.laid_chapter_number}章")
        if f.resolved_chapter_number:
            parts.append(f"回收=第{f.resolved_chapter_number}章")
        if f.description:
            parts.append(f"说明={_truncate(f.description, 200 if large_context else 90)}")
        foreshadow_lines.append("；".join(parts))

    storyline_rows = (
        db.query(StoryLine)
        .filter(
            StoryLine.project_id == project_id,
            StoryLine.status.in_(["planned", "active", "climax"]),
        )
        .order_by(StoryLine.sort_order)
        .all()
    )
    storyline_limit = 24 if large_context else 8
    storyline_lines = []
    for s in storyline_rows[:storyline_limit]:
        beats = list(s.key_beats or [])
        tail = ""
        if beats:
            last = beats[-1]
            if isinstance(last, dict):
                tail = str(last.get("beat") or last.get("milestone") or "")
            else:
                tail = str(last)
        storyline_lines.append(
            f"{s.name}（{s.line_type}/{s.status}）："
            f"{_truncate(tail or s.core_conflict or s.description, 260 if large_context else 120)}"
        )

    sections = []
    if index_lines:
        sections.append("章节索引（情节档案）：\n" + "\n".join(f"- {line}" for line in index_lines))
    if foreshadow_lines:
        sections.append("伏笔档案（含已回收/未回收）：\n" + "\n".join(f"- {line}" for line in foreshadow_lines))
    if storyline_lines:
        sections.append("故事线档案（活跃中）：\n" + "\n".join(f"- {line}" for line in storyline_lines))
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


class ChatMessageOut(BaseModel):
    id: UUID
    project_id: UUID
    chapter_id: Optional[UUID]
    context_type: str
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class ChatStreamRequest(BaseModel):
    prompt: str
    context_type: Literal["outline", "writing", "general"] = "general"
    chapter_id: Optional[UUID] = None
    """写作对话：将其他章节正文一并并入模型上下文（须属本书；当前章不必重复勾选，最多 8 章）。"""
    additional_chapter_ids: Optional[List[UUID]] = Field(default=None, max_length=8)
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


def _format_outline_chat_foreshadows(node: OutlineNode) -> str:
    parts: list[str] = []
    for label, value in [
        ("埋伏笔", node.foreshadows_laid),
        ("收伏笔", node.foreshadows_resolved),
    ]:
        if not value:
            continue
        descs = [
            item.get("description", "") if isinstance(item, dict) else str(item)
            for item in value[:5]
        ]
        text = "；".join(d for d in descs if d)
        if text:
            parts.append(f"{label}={text}")
    legacy = (node.extra or {}).get("foreshadow", "") if isinstance(node.extra, dict) else ""
    if legacy and not parts:
        parts.append(f"伏笔={legacy}")
    return "；".join(parts)


def _format_outline_chat_node(node: OutlineNode) -> str:
    node_type = {"volume": "卷", "arc": "篇", "chapter_plan": "章"}.get(node.node_type, node.node_type)
    parts = [f"- [{node_type}] {node.title}"]
    if node.summary:
        parts.append(f"核心事件：{_truncate(node.summary, 600)}")
    if node.hook:
        parts.append(f"开篇钩子：{_truncate(node.hook, 300)}")
    if node.conflict:
        parts.append(f"人物变化/冲突：{_truncate(node.conflict, 400)}")
    if node.highlight:
        parts.append(f"高光/章末：{_truncate(node.highlight, 400)}")
    if node.power_milestone:
        parts.append(f"实力里程碑：{_truncate(node.power_milestone, 300)}")
    if node.emotional_tone:
        parts.append(f"情感基调：{node.emotional_tone}")
    if node.pacing:
        parts.append(f"节奏：{node.pacing}")
    foreshadows = _format_outline_chat_foreshadows(node)
    if foreshadows:
        parts.append(foreshadows)
    extra = node.extra if isinstance(node.extra, dict) else {}
    for key, label in [("story_day", "故事日"), ("end_hook", "章末钩子"), ("pacing", "节奏补充")]:
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}：{_truncate(value, 220)}")
    return "；".join(parts)


def _format_outline_chat_context(
    *,
    project: Project,
    outline_nodes: list[OutlineNode],
    characters: list[Character],
    storylines: list[StoryLine],
    power_systems: list[PowerSystem],
) -> str:
    sections = [
        "【作品】",
        f"标题：{project.title}",
    ]
    if project.genre:
        sections.append(f"类型：{project.genre}")
    if project.logline:
        sections.append(f"一句话创意：{_truncate(project.logline, 800)}")
    if project.premise:
        sections.append(f"立意/故事核：{_truncate(project.premise, 1200)}")

    if characters:
        sections.append("\n【人物状态】")
        for c in characters[:80]:
            head = f"- {c.name}（{c.role}）"
            if c.current_realm:
                head += f"境界={c.current_realm}"
            parts = [head]
            if c.realm_rank is not None:
                parts.append(f"境界序号={c.realm_rank}")
            if c.current_status and c.current_status != "alive":
                parts.append(f"状态={c.current_status}")
            if c.current_location:
                parts.append(f"位置={c.current_location}")
            if c.motivation:
                parts.append(f"动机={_truncate(c.motivation, 240)}")
            sections.append("；".join(parts))

    if power_systems:
        sections.append("\n【力量体系】")
        for p in power_systems[:20]:
            level_names = []
            if isinstance(p.levels, list):
                level_names = [
                    item.get("name", "") if isinstance(item, dict) else str(item)
                    for item in p.levels[:20]
                ]
            parts = [f"- {p.name}（{p.system_type}）"]
            if p.description:
                parts.append(_truncate(p.description, 500))
            if p.breakthrough_condition:
                parts.append(f"突破条件={_truncate(p.breakthrough_condition, 400)}")
            if level_names:
                parts.append("境界序列=" + " > ".join(n for n in level_names if n))
            sections.append("；".join(parts))

    if storylines:
        sections.append("\n【故事线】")
        for s in storylines[:40]:
            parts = [f"- {s.name}（{s.line_type}/{s.status}）"]
            if s.core_conflict or s.description:
                parts.append(_truncate(s.core_conflict or s.description, 500))
            if s.key_beats:
                parts.append(f"关键节拍={json.dumps(s.key_beats, ensure_ascii=False)[:1200]}")
            sections.append("；".join(parts))

    sections.append("\n【大纲树】")
    if outline_nodes:
        for node in outline_nodes[:600]:
            sections.append(_format_outline_chat_node(node))
    else:
        sections.append("（暂无大纲节点）")

    return "\n".join(sections)


def _format_writing_chat_context(
    *,
    project: Project,
    chapter: Chapter,
    outline_node: Optional[OutlineNode],
    prev_chapter: Optional[Chapter],
) -> str:
    sections = [
        "【作品】",
        f"标题：{project.title}",
    ]
    if project.genre:
        sections.append(f"类型：{project.genre}")
    if project.premise:
        sections.append(f"立意/故事核：{_truncate(project.premise, 1200)}")

    sections.append("\n【当前章节】")
    sections.append(f"标题：{chapter.title}")
    sections.append(f"章节序号：{display_chapter_number(chapter.title, chapter.sort_order)}")

    if outline_node:
        sections.append("\n【当前章节大纲】")
        sections.append(_format_outline_chat_node(outline_node))

    if prev_chapter and prev_chapter.content:
        prev_plain = _plain_text(prev_chapter.content)
        sections.append("\n【上一章结尾】")
        sections.append(prev_plain[-1800:])

    sections.append("\n【当前章节正文】")
    plain = _plain_text(chapter.content)
    sections.append(plain if plain else "（当前章节暂无正文）")
    return "\n".join(sections)


def _append_reference_chapters_to_writing_context(
    db: Session,
    *,
    project_id: str,
    anchor_chapter_id: UUID,
    additional_chapter_ids: Optional[List[UUID]],
    base_context: str,
) -> str:
    if not additional_chapter_ids:
        return base_context
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for raw in additional_chapter_ids:
        if raw == anchor_chapter_id:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        ordered.append(raw)
        if len(ordered) >= 8:
            break
    if not ordered:
        return base_context
    rows = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.id.in_(ordered))
        .all()
    )
    by_id = {c.id: c for c in rows}
    blocks: list[str] = []
    for cid in ordered:
        ch = by_id.get(cid)
        if not ch:
            continue
        pl = _plain_text(ch.content)
        narr, _ = split_plain_manuscript_and_index_block(pl)
        body = (narr.strip() if narr.strip() else pl)[:12000]
        num = display_chapter_number(ch.title, ch.sort_order)
        blocks.append(
            f"【参考章节《{ch.title}》（序号：{num}）】\n{body or '（该章暂无正文）'}"
        )
    if not blocks:
        return base_context
    return (
        base_context
        + "\n\n【作者指定参考的其他章节（仅作对话依据；当前章见上文）】\n"
        + "\n\n".join(blocks)
    )


class ChapterCoherenceCheckRequest(BaseModel):
    chapter_ids: List[str]
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class SaveChapterCoherenceReportRequest(BaseModel):
    name: Optional[str] = None
    model_profile: Literal["local", "gemini"] = "local"
    selected_chapter_ids: List[str]
    result: dict


class ChapterCoherenceApplyPreviewRequest(BaseModel):
    report_id: UUID
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class CoherenceApplyRevisionItem(BaseModel):
    chapter_id: UUID
    revised_content: str


class ChapterCoherenceApplyCommitRequest(BaseModel):
    report_id: UUID
    revisions: List[CoherenceApplyRevisionItem]


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

    memory_query = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc())
    )
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
            highest_level = "未知"
            if ps.levels:
                last_level = ps.levels[-1]
                if isinstance(last_level, dict):
                    highest_level = last_level.get("name", "") or "未知"
                else:
                    highest_level = str(last_level) or "未知"
            power_systems_summary.append(
                f"{ps.name}：最高境界={highest_level}，主角当前={ps.protagonist_current_rank or '未知'}"
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
    plot_dossier_context = _build_plot_dossier_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        large_context=large_context,
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
        settings_summary=[
            _format_world_setting_context(s, content_limit=2400 if large_context else 260)
            for s in settings
        ],
        check_types=req.check_types,
        character_states=character_states,
        storylines_context=storylines_context,
        power_systems_summary=power_systems_summary,
        outline_context=outline_context,
        continuity_context=continuity_context,
        chapter_index_context=chapter_index_context,
        plot_dossier_context=plot_dossier_context,
    )

    # 缓存质检结果
    chapter.last_quality_score = result.get("overall_score")
    chapter.last_quality_report = result
    chapter.quality_checked_at = func.now()
    _sync_quality_debts(db, project_id, chapter, result)
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
    sort_orders = [c.sort_order for c in chapters]
    min_so = min(sort_orders)
    max_so = max(sort_orders)

    project_context_parts = []
    if project.premise:
        project_context_parts.append(f"作品基本面：{_truncate(project.premise, 4000 if large_context else 600)}")

    settings = db.query(WorldSetting).filter(WorldSetting.project_id == project_id).all()
    if settings:
        setting_limit = 60 if large_context else 8
        setting_len = 1200 if large_context else 160
        project_context_parts.append(
            "世界观设定：\n" + "\n".join(
                f"- {_format_world_setting_context(s, content_limit=setting_len)}"
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

    index_rows = (
        db.query(ChapterIndex, Chapter)
        .join(Chapter, Chapter.id == ChapterIndex.chapter_id)
        .filter(
            ChapterIndex.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order <= max_so,
        )
        .order_by(Chapter.sort_order)
        .all()
    )
    if index_rows:
        index_window = [
            (idx, ch) for idx, ch in index_rows
            if large_context or ch.sort_order >= max(0, min_so - 5)
        ]
        project_context_parts.append(
            "章节索引与伏笔：\n" + "\n".join(
                f"- 第{display_chapter_number(ch.title, ch.sort_order)}章：核心事件={json.dumps(idx.core_events or [], ensure_ascii=False)[:700]}; "
                f"章末钩子={idx.ending_hook or ''}; "
                f"未回收/已回收伏笔={json.dumps(idx.actual_foreshadows_laid or [], ensure_ascii=False)[:700]} / "
                f"{json.dumps(idx.actual_foreshadows_resolved or [], ensure_ascii=False)[:700]}"
                for idx, ch in index_window
            )
        )

    memory_rows = (
        db.query(MemoryChunk, Chapter)
        .join(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(
            MemoryChunk.project_id == project_id,
            Chapter.project_id == project_id,
            Chapter.sort_order <= max_so,
        )
        .order_by(Chapter.sort_order.desc())
        .limit(100 if large_context else 20)
        .all()
    )
    if memory_rows:
        project_context_parts.append(
            "记忆库：\n" + "\n".join(
                f"- 第{display_chapter_number(ch.title, ch.sort_order)}章 {m.title or m.memory_type}: {_truncate(m.content, 700 if large_context else 120)}"
                for m, ch in memory_rows
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
        "apply_events": report.apply_events or [],
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
            "apply_events": r.apply_events or [],
            "created_at": r.created_at,
        }
        for r in reports
    ]


_MAX_COHERENCE_APPLY_CHAPTERS = 12


@router.post("/chapter-coherence-apply/preview")
async def chapter_coherence_apply_preview(
    project_id: str,
    req: ChapterCoherenceApplyPreviewRequest,
    db: Session = Depends(get_db),
):
    """
    根据已保存的连贯性评测记录，调用模型生成「最小幅度」正文修订预览（不写库）。
    远程 Gemini 建议一次处理多章；本地模型按章顺序调用。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    report = (
        db.query(ChapterCoherenceReport)
        .filter(
            ChapterCoherenceReport.id == req.report_id,
            ChapterCoherenceReport.project_id == project_id,
        )
        .first()
    )
    if not report:
        raise HTTPException(404, "评测记录不存在或不属于当前项目")

    result = report.result if isinstance(report.result, dict) else {}
    if result.get("error"):
        raise HTTPException(400, "该评测记录解析失败，无法用于修订正文")

    raw_ids = report.selected_chapter_ids or []
    if len(raw_ids) < 2:
        raise HTTPException(400, "该评测记录章节数不足")
    if len(raw_ids) > _MAX_COHERENCE_APPLY_CHAPTERS:
        raise HTTPException(
            400,
            f"一次最多修订 {_MAX_COHERENCE_APPLY_CHAPTERS} 章，请拆分评测记录后再试",
        )

    chapters = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.id.in_(raw_ids))
        .all()
    )
    if len(chapters) != len(set(raw_ids)):
        raise HTTPException(400, "记录中的章节已不存在或不属于本项目，无法修订")

    order = {str(cid): i for i, cid in enumerate(raw_ids)}
    chapters = sorted(chapters, key=lambda c: order.get(str(c.id), 9999))

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
    try:
        rows = await svc.apply_coherence_revisions(
            project_title=project.title,
            coherence=result,
            chapters=payload,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e

    out = []
    for row in rows:
        cid = row.get("chapter_id")
        ch = next((c for c in chapters if str(c.id) == str(cid)), None)
        title = ch.title if ch else ""
        unchanged = bool(row.get("unchanged"))
        revised = (row.get("revised_content") or "").strip()
        orig = (ch.content or "") if ch else ""
        out.append(
            {
                "chapter_id": str(cid),
                "chapter_title": title,
                "unchanged": unchanged or not revised,
                "change_note": row.get("change_note") or "",
                "revised_content": "" if unchanged or not revised else revised,
                "previous_plain_preview": _plain_text(orig)[:320],
                "revised_plain_preview": _plain_text(revised if revised else orig)[:320],
            }
        )

    return {
        "report_id": str(report.id),
        "revisions": out,
    }


@router.post("/chapter-coherence-apply/commit")
def chapter_coherence_apply_commit(
    project_id: str,
    req: ChapterCoherenceApplyCommitRequest,
    db: Session = Depends(get_db),
):
    """将预览阶段返回的修订写入章节正文（每条须有非空 revised_content）。"""
    from app.routers.chapters import count_words, normalize_chapter_sort_orders

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    report = (
        db.query(ChapterCoherenceReport)
        .filter(
            ChapterCoherenceReport.id == req.report_id,
            ChapterCoherenceReport.project_id == project_id,
        )
        .first()
    )
    if not report:
        raise HTTPException(404, "评测记录不存在或不属于当前项目")

    allowed = {str(x) for x in (report.selected_chapter_ids or [])}
    applied = []
    for item in req.revisions:
        cid = str(item.chapter_id)
        if cid not in allowed:
            raise HTTPException(400, f"章节 {cid} 不在该评测记录所选范围内")
        text = (item.revised_content or "").strip()
        if not text:
            continue
        chapter = (
            db.query(Chapter)
            .filter(Chapter.id == cid, Chapter.project_id == project_id)
            .first()
        )
        if not chapter:
            raise HTTPException(404, f"章节不存在: {cid}")
        if (chapter.content or "").strip() == text:
            applied.append({"chapter_id": cid, "skipped": True, "reason": "与当前正文相同"})
            continue

        snap = ChapterVersion(
            chapter_id=chapter.id,
            content=chapter.content,
            word_count=chapter.word_count,
            note="连贯性评测修订前快照",
            is_auto=True,
        )
        db.add(snap)
        chapter.content = text
        chapter.word_count = count_words(text)
        applied.append({"chapter_id": cid, "skipped": False, "word_count": chapter.word_count})

    if applied:
        events = list(report.apply_events) if report.apply_events else []
        events.append(
            {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "applied": applied,
            }
        )
        report.apply_events = events

    db.commit()
    db.refresh(report)
    normalize_chapter_sort_orders(db, project_id)
    return {
        "report_id": str(req.report_id),
        "applied": applied,
        "apply_events": report.apply_events or [],
    }


# ── AI 对话（持久化 + 上下文感知）──────────────────────
def _chat_context_label(context_type: str, chapter: Optional[Chapter] = None) -> str:
    if context_type == "outline":
        return "大纲"
    if context_type == "writing":
        return f"当前章节正文：{chapter.title if chapter else '未选择章节'}"
    return "项目"


def _query_chat_messages(
    db: Session,
    *,
    project_id: str,
    context_type: str,
    chapter_id: Optional[UUID],
):
    query = db.query(AiChatMessage).filter(
        AiChatMessage.project_id == project_id,
        AiChatMessage.context_type == context_type,
    )
    if chapter_id:
        query = query.filter(AiChatMessage.chapter_id == chapter_id)
    else:
        query = query.filter(AiChatMessage.chapter_id.is_(None))
    return query


@router.get("/chat/messages", response_model=List[ChatMessageOut])
def list_chat_messages(
    project_id: str,
    context_type: Literal["outline", "writing", "general"] = "general",
    chapter_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    return _query_chat_messages(
        db,
        project_id=project_id,
        context_type=context_type,
        chapter_id=chapter_id,
    ).order_by(AiChatMessage.created_at.asc()).limit(200).all()


@router.post("/chat/stream")
async def chat_stream(
    project_id: str,
    req: ChatStreamRequest,
    db: Session = Depends(get_db),
):
    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(400, "请输入对话内容")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    chapter: Optional[Chapter] = None
    context_text = ""
    if req.context_type == "outline":
        outline_nodes = db.query(OutlineNode).filter(
            OutlineNode.project_id == project_id
        ).order_by(OutlineNode.sort_order).all()
        characters = db.query(Character).filter(Character.project_id == project_id).all()
        storylines = db.query(StoryLine).filter(StoryLine.project_id == project_id).order_by(StoryLine.sort_order).all()
        power_systems = db.query(PowerSystem).filter(PowerSystem.project_id == project_id).order_by(PowerSystem.sort_order).all()
        context_text = _format_outline_chat_context(
            project=project,
            outline_nodes=outline_nodes,
            characters=characters,
            storylines=storylines,
            power_systems=power_systems,
        )
    elif req.context_type == "writing":
        if not req.chapter_id:
            raise HTTPException(400, "写作对话需要当前章节")
        chapter = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not chapter:
            raise HTTPException(404, "Chapter not found")
        outline_node = None
        if chapter.outline_node_id:
            outline_node = db.query(OutlineNode).filter(
                OutlineNode.id == chapter.outline_node_id,
                OutlineNode.project_id == project_id,
            ).first()
        prev_chapter = db.query(Chapter).filter(
            Chapter.project_id == project_id,
            Chapter.sort_order < chapter.sort_order,
        ).order_by(Chapter.sort_order.desc()).first()
        context_text = _format_writing_chat_context(
            project=project,
            chapter=chapter,
            outline_node=outline_node,
            prev_chapter=prev_chapter,
        )
        context_text = _append_reference_chapters_to_writing_context(
            db,
            project_id=project_id,
            anchor_chapter_id=chapter.id,
            additional_chapter_ids=req.additional_chapter_ids,
            base_context=context_text,
        )
    else:
        context_text = "\n".join([
            "【作品】",
            f"标题：{project.title}",
            f"类型：{project.genre or '未设置'}",
            f"一句话创意：{_truncate(project.logline, 800) or '未设置'}",
            f"立意/故事核：{_truncate(project.premise, 1200) or '未设置'}",
        ])

    existing_messages = _query_chat_messages(
        db,
        project_id=project_id,
        context_type=req.context_type,
        chapter_id=req.chapter_id if req.context_type == "writing" else None,
    ).order_by(AiChatMessage.created_at.desc()).limit(12).all()
    chat_history = [
        {"role": item.role, "content": item.content}
        for item in reversed(existing_messages)
    ]

    user_message = AiChatMessage(
        project_id=project_id,
        chapter_id=req.chapter_id if req.context_type == "writing" else None,
        context_type=req.context_type,
        role="user",
        content=prompt,
    )
    db.add(user_message)
    db.commit()

    # StreamingResponse 返回后 get_db 会先关闭 Session；不得在 event_stream 内再读 ORM（会触发 DetachedInstanceError）
    context_label = _chat_context_label(req.context_type, chapter)

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        chunks: list[str] = []
        try:
            async for chunk in svc.chat_stream(
                user_prompt=prompt,
                context_label=context_label,
                context_text=context_text,
                chat_history=chat_history,
            ):
                chunks.append(chunk)
                yield f"data: {json.dumps({'text': chunk})}\n\n"
            assistant_text = "".join(chunks).strip()
            if assistant_text:
                db.add(AiChatMessage(
                    project_id=project_id,
                    chapter_id=req.chapter_id if req.context_type == "writing" else None,
                    context_type=req.context_type,
                    role="assistant",
                    content=assistant_text,
                ))
                db.commit()
        except Exception as exc:
            db.rollback()
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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

    chapter_content_snapshot = chapter.content or ""
    suggest_prompt = req.prompt

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        async for chunk in svc.suggest_stream(
            chapter_content=chapter_content_snapshot,
            user_prompt=suggest_prompt,
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

    chapter_no = display_chapter_number(chapter.title, chapter.sort_order)
    svc = AIService(
        "gemini" if model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=llm_provider_id,
    )
    extracted = await svc.extract_memory(
        chapter_content=chapter.content,
        chapter_title=chapter.title,
        chapter_number=chapter_no,
    )

    results = []
    for item in extracted:
        chunk = MemoryChunk(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter_no,
            **item
        )
        db.add(chunk)
        results.append(chunk)
    db.commit()
    for r in results:
        db.refresh(r)

    # 异步向量化（不阻塞响应）
    for r in results:
        embed_text = f"{r.title or ''}\n{r.content}".strip()
        embed_chunk_async(r.id, embed_text, SessionLocal)

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

    if req.replace_existing:
        from app.routers.chapters import clear_chapter_rewrite_derivatives

        clear_chapter_rewrite_derivatives(db, project_id, req.chapter_id)
        db.commit()
        db.refresh(chapter)

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
            f"- {_format_world_setting_context(s, content_limit=2400)}"
            for s in settings
        )
    else:
        world_summary = " | ".join(
            _format_world_setting_context(s, content_limit=120).replace("\n", "；")
            for s in settings[:8]
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
    mem_rows_draft = (
        db.query(MemoryChunk, Chapter)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
        .order_by(func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, -1).desc())
        .limit(80 if large_context else 12)
        .all()
    )
    if large_context:
        memory_summary = "\n".join(
            f"- 第{display_chapter_number(ch.title, ch.sort_order) if ch is not None else (m.chapter_number or '?')}章 "
            f"{m.title or m.memory_type}: {_truncate(m.content, 600)}"
            for m, ch in mem_rows_draft
        )
    else:
        memory_summary = " | ".join(
            f"{m.title or m.memory_type}: {m.content[:60]}" for m, _ch in mem_rows_draft
        )

    # ── 上一章结尾（衔接用）──────────────────────────
    prev_chapter = db.query(Chapter).filter(
        Chapter.project_id == project_id,
        Chapter.sort_order < chapter.sort_order,
    ).order_by(Chapter.sort_order.desc()).first()

    prev_tail = ""
    if prev_chapter and prev_chapter.content:
        prev_plain = _plain_text(prev_chapter.content)
        prev_body, _ = split_plain_manuscript_and_index_block(prev_plain)
        base_prev = prev_body.strip() if prev_body.strip() else prev_plain
        clean = _strip_tail_meta_lines(base_prev)
        prev_limit = 3000 if large_context else 400
        prev_tail = clean[-prev_limit:] if len(clean) > prev_limit else clean

    # ── 当前章节正文（strip HTML；业务库仅存叙事时不再带入稿末块）──
    existing_content = _plain_text(chapter.content)
    narr_existing, _ = split_plain_manuscript_and_index_block(existing_content)
    if narr_existing.strip():
        existing_content = narr_existing.strip()
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
    writing_brief_context = _build_writing_brief_context(
        db=db,
        project_id=project_id,
        chapter=chapter,
        outline_node=outline_node,
        large_context=large_context,
    )
    plot_dossier_context = _build_plot_dossier_context(
        db, project_id, chapter, large_context=large_context
    )
    quality_debt_context = _build_quality_debt_context(
        _pending_quality_debts_for_chapter(
            db=db,
            project_id=project_id,
            chapter=chapter,
            limit=12 if large_context else 6,
        )
    )

    # StreamingResponse 返回后 Session 会关闭；此处一次性读出 draft_assist_stream 所需的 ORM 字段
    def _fmt_foreshadows_for_stream(node) -> str:
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
        if not parts:
            legacy = (node.extra or {}).get("foreshadow", "")
            if legacy:
                return legacy
        return "  ".join(parts)

    outline_foreshadow_str = _fmt_foreshadows_for_stream(outline_node)
    story_day_str = (outline_node.extra or {}).get("story_day", "") if outline_node else ""
    if outline_node:
        word_target_val = int(
            (outline_node.expected_words if outline_node.expected_words else None)
            or (outline_node.extra or {}).get("word_estimate")
            or 2300
        )
    else:
        word_target_val = 2300
    chapter_title_str = chapter.title or ""
    outline_hook_str = outline_node.hook or "" if outline_node else ""
    outline_summary_str = outline_node.summary or "" if outline_node else ""
    outline_conflict_str = outline_node.conflict or "" if outline_node else ""
    outline_highlight_str = outline_node.highlight or "" if outline_node else ""
    outline_power_milestone_str = outline_node.power_milestone or "" if outline_node else ""
    outline_emotional_tone_str = outline_node.emotional_tone or "" if outline_node else ""
    premise_str = project.premise or ""
    user_prompt_str = req.user_prompt or ""
    stream_log_ctx = {"project_id": str(project_id), "chapter_id": str(req.chapter_id)}

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    async def event_stream():
        try:
            async for chunk in svc.draft_assist_stream(
                chapter_title=chapter_title_str,
                outline_hook=outline_hook_str,
                outline_summary=outline_summary_str,
                outline_conflict=outline_conflict_str,
                outline_highlight=outline_highlight_str,
                outline_foreshadow=outline_foreshadow_str,
                outline_power_milestone=outline_power_milestone_str,
                outline_emotional_tone=outline_emotional_tone_str,
                story_day=story_day_str,
                chapter_manifest=chapter_manifest_names,
                prev_chapter_tail=prev_tail,
                world_summary=world_summary,
                character_summary=char_summary,
                storyline_summary=storyline_summary,
                memory_summary=memory_summary,
                existing_content=existing_content,
                premise=premise_str,
                user_prompt=user_prompt_str,
                replace_existing=req.replace_existing,
                continuity_context=continuity_context,
                chapter_index_context=chapter_index_context,
                quality_debt_context=quality_debt_context,
                writing_brief_context=writing_brief_context,
                plot_dossier_context=plot_dossier_context,
                word_target=word_target_val,
                stream_log_context=stream_log_ctx,
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


class NewItemAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    item_type: str = "artifact"
    rarity: str = "rare"
    description: Optional[str] = None
    origin: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    current_owner_id: Optional[str] = None
    current_owner_name: Optional[str] = None
    story_significance: Optional[str] = None
    status: str = "intact"
    reason_to_store: Optional[str] = None


class ItemAssetUpdate(BaseModel):
    item_id: Optional[str] = None
    item_name: Optional[str] = None
    status: Optional[str] = None
    current_owner_id: Optional[str] = None
    current_owner_name: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    story_significance: Optional[str] = None
    event_note: Optional[str] = None


class NewSkillAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    skill_type: str = "combat"
    grade: str = "earth"
    source: Optional[str] = None
    level_required: Optional[str] = None
    prerequisites: Optional[str] = None
    description: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    mastered_by_character_ids: List[str] = Field(default_factory=list)
    mastered_by_character_names: List[str] = Field(default_factory=list)
    reason_to_store: Optional[str] = None


class SkillAssetUpdate(BaseModel):
    skill_id: Optional[str] = None
    skill_name: Optional[str] = None
    effects: Optional[str] = None
    limitations: Optional[str] = None
    add_mastered_by_character_id: Optional[str] = None
    add_mastered_by_character_name: Optional[str] = None
    mastery: Optional[str] = None
    event_note: Optional[str] = None


class NewFactionAsset(BaseModel):
    tier: Literal["A", "B", "C"] = "B"
    name: str
    faction_type: str = "other"
    alignment: str = "neutral"
    description: Optional[str] = None
    territory: Optional[str] = None
    strength_level: Optional[str] = None
    goals: Optional[str] = None
    resources: Optional[str] = None
    attitude_to_protagonist: str = "neutral"
    reason_to_store: Optional[str] = None


class FactionAssetUpdate(BaseModel):
    faction_id: Optional[str] = None
    faction_name: Optional[str] = None
    alignment: Optional[str] = None
    goals: Optional[str] = None
    resources: Optional[str] = None
    attitude_to_protagonist: Optional[str] = None
    event_note: Optional[str] = None


class AssetUpdates(BaseModel):
    new_items: List[NewItemAsset] = Field(default_factory=list)
    item_updates: List[ItemAssetUpdate] = Field(default_factory=list)
    new_skills: List[NewSkillAsset] = Field(default_factory=list)
    skill_updates: List[SkillAssetUpdate] = Field(default_factory=list)
    new_factions: List[NewFactionAsset] = Field(default_factory=list)
    faction_updates: List[FactionAssetUpdate] = Field(default_factory=list)

class ChapterIndexPayload(BaseModel):
    story_day: Optional[str] = None
    core_events: List[dict | str] = []
    first_appearances: List[dict] = []
    actual_foreshadows_laid: List[dict] = []
    actual_foreshadows_resolved: List[dict] = []
    ending_hook: Optional[str] = None
    hook_strength: int = 1
    continuity_notes: List[dict | str] = []

class NewCharacterPayload(BaseModel):
    """auto_debrief 从正文识别出的新配角，由 chapter_debrief 写入 DB。"""
    name: str
    role: str = "supporting"
    gender: Optional[str] = None
    age: Optional[str] = None
    faction: Optional[str] = None
    personality: Optional[str] = None
    motivation: Optional[str] = None
    background: Optional[str] = None
    current_realm: Optional[str] = None
    current_status: Optional[str] = "alive"
    current_location: Optional[str] = None
    arc_scope: Optional[str] = "mini_arc"   # single_chapter / mini_arc / long_arc
    author_notes: Optional[str] = None


class ChapterDebriefRequest(BaseModel):
    chapter_id: str
    character_updates: List[CharacterUpdate] = []
    storyline_updates: List[StoryLineUpdate] = []
    memory_updates: List[MemoryUpdate] = []
    asset_updates: AssetUpdates = Field(default_factory=AssetUpdates)
    new_characters: List[NewCharacterPayload] = []   # 本章新出场、值得入库的配角
    chapter_index: Optional[ChapterIndexPayload] = None
    notes: Optional[str] = None           # 作者备注，存到 chapter


def _safe_uuid(raw: Optional[str]):
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except Exception:
        return None


def _find_character(
    db: Session,
    project_id: str,
    character_id: Optional[str] = None,
    character_name: Optional[str] = None,
) -> Optional[Character]:
    character_uuid = _safe_uuid(character_id)
    if character_uuid:
        found = db.query(Character).filter(
            Character.id == character_uuid,
            Character.project_id == project_id,
        ).first()
        if found:
            return found
    if character_name:
        return db.query(Character).filter(
            Character.name == character_name,
            Character.project_id == project_id,
        ).first()
    return None


def _find_asset_by_id_or_name(
    db: Session,
    model,
    project_id: str,
    asset_id: Optional[str],
    asset_name: Optional[str],
):
    asset_uuid = _safe_uuid(asset_id)
    if asset_uuid:
        found = db.query(model).filter(
            model.id == asset_uuid,
            model.project_id == project_id,
        ).first()
        if found:
            return found
    if asset_name:
        return db.query(model).filter(
            model.project_id == project_id,
            model.name == asset_name,
        ).first()
    return None


def _merge_extra(existing: Optional[dict], **updates) -> dict:
    base = dict(existing or {})
    for key, value in updates.items():
        if value not in (None, "", []):
            base[key] = value
    return base


def _link_item_to_character(character: Optional[Character], item: Item, chapter_number: int) -> None:
    if not character:
        return
    items = list(character.owned_items or [])
    item_id = str(item.id)
    if not any(
        isinstance(entry, dict)
        and (str(entry.get("item_id")) == item_id or entry.get("item_name") == item.name)
        for entry in items
    ):
        items.append({
            "item_id": item_id,
            "item_name": item.name,
            "acquired_chapter": chapter_number,
        })
    character.owned_items = items


def _link_skill_to_character(
    character: Optional[Character],
    skill: Skill,
    mastery: Optional[str],
) -> None:
    if not character:
        return
    skills = list(character.known_skills or [])
    skill_id = str(skill.id)
    existing_ids = {
        str(entry.get("skill_id"))
        for entry in skills
        if isinstance(entry, dict) and entry.get("skill_id")
    }
    if skill_id in existing_ids:
        character.known_skills = [
            {
                **entry,
                "mastery": mastery or entry.get("mastery"),
            }
            if isinstance(entry, dict) and str(entry.get("skill_id")) == skill_id
            else entry
            for entry in skills
        ]
        return
    skills.append({
        "skill_id": skill_id,
        "skill_name": skill.name,
        "mastery": mastery or "初学",
    })
    character.known_skills = skills


def _append_unique_uuid(values: Optional[list], value) -> list:
    result = [str(v) for v in (values or []) if v]
    text = str(value)
    if text not in result:
        result.append(text)
    return result


def _apply_asset_updates(
    db: Session,
    project_id: str,
    chapter: Chapter,
    asset_updates: AssetUpdates,
) -> dict:
    """Persist durable A/B assets; C-tier assets stay as prose/memory only."""
    chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    stats = {
        "created_items": 0,
        "updated_items": 0,
        "created_skills": 0,
        "updated_skills": 0,
        "created_factions": 0,
        "updated_factions": 0,
    }

    for data in asset_updates.new_items:
        name = (data.name or "").strip()
        if not name or data.tier == "C":
            continue
        owner = _find_character(db, project_id, data.current_owner_id, data.current_owner_name)
        item = _find_asset_by_id_or_name(db, Item, project_id, None, name)
        if item:
            stats["updated_items"] += 1
        else:
            item = Item(id=uuid4(), project_id=project_id, name=name)
            db.add(item)
            stats["created_items"] += 1
        item.item_type = data.item_type or item.item_type
        item.rarity = data.rarity or item.rarity
        item.description = data.description or item.description
        item.origin = data.origin or item.origin
        item.effects = data.effects or item.effects
        item.limitations = data.limitations or item.limitations
        item.current_owner_id = owner.id if owner else item.current_owner_id
        item.story_significance = data.story_significance or item.story_significance
        item.first_appearance_chapter = item.first_appearance_chapter or chapter_number
        item.status = data.status or item.status
        item.extra = _merge_extra(
            item.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )
        if owner:
            history = list(item.ownership_history or [])
            history.append({
                "owner_name": owner.name,
                "chapter": chapter_number,
                "event_description": data.reason_to_store or f"第{chapter_number}章首次纳入资产库",
            })
            item.ownership_history = history
            _link_item_to_character(owner, item, chapter_number)

    for data in asset_updates.item_updates:
        item = _find_asset_by_id_or_name(db, Item, project_id, data.item_id, data.item_name)
        if not item:
            continue
        owner = _find_character(db, project_id, data.current_owner_id, data.current_owner_name)
        item.status = data.status or item.status
        item.effects = data.effects or item.effects
        item.limitations = data.limitations or item.limitations
        item.story_significance = data.story_significance or item.story_significance
        if owner:
            item.current_owner_id = owner.id
            history = list(item.ownership_history or [])
            history.append({
                "owner_name": owner.name,
                "chapter": chapter_number,
                "event_description": data.event_note or f"第{chapter_number}章持有者更新",
            })
            item.ownership_history = history
            _link_item_to_character(owner, item, chapter_number)
        item.extra = _merge_extra(item.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_items"] += 1

    for data in asset_updates.new_skills:
        name = (data.name or "").strip()
        if not name or data.tier == "C":
            continue
        skill = _find_asset_by_id_or_name(db, Skill, project_id, None, name)
        if skill:
            stats["updated_skills"] += 1
        else:
            skill = Skill(id=uuid4(), project_id=project_id, name=name)
            db.add(skill)
            stats["created_skills"] += 1
        skill.skill_type = data.skill_type or skill.skill_type
        skill.grade = data.grade or skill.grade
        skill.source = data.source or skill.source
        skill.level_required = data.level_required or skill.level_required
        skill.prerequisites = data.prerequisites or skill.prerequisites
        skill.description = data.description or skill.description
        skill.effects = data.effects or skill.effects
        skill.limitations = data.limitations or skill.limitations
        skill.first_appearance_chapter = skill.first_appearance_chapter or chapter_number
        skill.extra = _merge_extra(
            skill.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )
        mastered_ids = list(skill.mastered_by_character_ids or [])
        for char_id in data.mastered_by_character_ids:
            character = _find_character(db, project_id, char_id, None)
            if character:
                mastered_ids = _append_unique_uuid(mastered_ids, character.id)
                _link_skill_to_character(character, skill, None)
        for char_name in data.mastered_by_character_names:
            character = _find_character(db, project_id, None, char_name)
            if character:
                mastered_ids = _append_unique_uuid(mastered_ids, character.id)
                _link_skill_to_character(character, skill, None)
        skill.mastered_by_character_ids = mastered_ids

    for data in asset_updates.skill_updates:
        skill = _find_asset_by_id_or_name(db, Skill, project_id, data.skill_id, data.skill_name)
        if not skill:
            continue
        skill.effects = data.effects or skill.effects
        skill.limitations = data.limitations or skill.limitations
        character = _find_character(
            db,
            project_id,
            data.add_mastered_by_character_id,
            data.add_mastered_by_character_name,
        )
        if character:
            skill.mastered_by_character_ids = _append_unique_uuid(skill.mastered_by_character_ids, character.id)
            _link_skill_to_character(character, skill, data.mastery)
        skill.extra = _merge_extra(skill.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_skills"] += 1

    for data in asset_updates.new_factions:
        name = (data.name or "").strip()
        if not name or data.tier == "C":
            continue
        faction = _find_asset_by_id_or_name(db, Faction, project_id, None, name)
        if faction:
            stats["updated_factions"] += 1
        else:
            faction = Faction(id=uuid4(), project_id=project_id, name=name)
            db.add(faction)
            stats["created_factions"] += 1
        faction.faction_type = data.faction_type or faction.faction_type
        faction.alignment = data.alignment or faction.alignment
        faction.description = data.description or faction.description
        faction.territory = data.territory or faction.territory
        faction.strength_level = data.strength_level or faction.strength_level
        faction.goals = data.goals or faction.goals
        faction.resources = data.resources or faction.resources
        faction.attitude_to_protagonist = data.attitude_to_protagonist or faction.attitude_to_protagonist
        faction.extra = _merge_extra(
            faction.extra,
            asset_tier=data.tier,
            reason_to_store=data.reason_to_store,
            first_recorded_chapter=chapter_number,
        )

    for data in asset_updates.faction_updates:
        faction = _find_asset_by_id_or_name(db, Faction, project_id, data.faction_id, data.faction_name)
        if not faction:
            continue
        faction.alignment = data.alignment or faction.alignment
        faction.goals = data.goals or faction.goals
        faction.resources = data.resources or faction.resources
        faction.attitude_to_protagonist = data.attitude_to_protagonist or faction.attitude_to_protagonist
        faction.extra = _merge_extra(faction.extra, last_update_note=data.event_note, last_update_chapter=chapter_number)
        stats["updated_factions"] += 1

    return stats


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
    _new_memory_chunks: List[MemoryChunk] = []  # 用于批量触发 embedding
    chapter_index_saved = False
    chapter_index_error: Optional[str] = None
    synced_foreshadows = {"created": 0, "updated": 0, "resolved": 0}
    asset_stats = {
        "created_items": 0,
        "updated_items": 0,
        "created_skills": 0,
        "updated_skills": 0,
        "created_factions": 0,
        "updated_factions": 0,
    }

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

        # 主角境界快照供「境界时间轴」只读聚合（提交后 debrief 缓存会删除，故落 extra）
        if getattr(char, "role", None) == "protagonist" and (
            cu.current_realm is not None or cu.realm_rank is not None
        ):
            realm_label = (
                (cu.current_realm.strip()[:100] if isinstance(cu.current_realm, str) else "")
                or (char.current_realm or "").strip()[:100]
            )
            rank_snap = cu.realm_rank if cu.realm_rank is not None else char.realm_rank
            if realm_label or rank_snap is not None:
                chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
                extra = dict(char.extra) if isinstance(char.extra, dict) else {}
                hist = [h for h in (extra.get("debrief_realm_milestones") or []) if isinstance(h, dict)]
                hist = [h for h in hist if int(h.get("chapter_number") or -1) != chapter_num]
                hist.append(
                    {
                        "chapter_number": chapter_num,
                        "chapter_title": (chapter.title or "")[:300],
                        "realm_name": realm_label,
                        "realm_rank": rank_snap,
                        "source": "chapter_debrief",
                    }
                )
                hist.sort(key=lambda h: int(h.get("chapter_number") or 0))
                extra["debrief_realm_milestones"] = hist
                char.extra = extra
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
                "chapter": display_chapter_number(chapter.title, chapter.sort_order),
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
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            memory_type=mu.memory_type,
            title=(mu.title or mu.memory_type).strip()[:200],
            content=content,
            tags=mu.tags[:8],
        )
        db.add(memory)
        _new_memory_chunks.append(memory)
        added_memories.append(memory.title or memory.memory_type)

    # ── 写入/更新结构化资产（实体状态），与 memory_updates 的事件证据互补 ──
    if req.asset_updates:
        asset_stats = _apply_asset_updates(
            db=db,
            project_id=project_id,
            chapter=chapter,
            asset_updates=req.asset_updates,
        )

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
                data["chapter_number"] = display_chapter_number(chapter.title, chapter.sort_order)
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

    # ── 新配角入库（auto_debrief 从正文识别，tier=supporting/emergent）────
    added_new_characters: List[str] = []
    if req.new_characters:
        existing_names = {
            c.name for c in db.query(Character.name).filter(
                Character.project_id == project_id
            ).all()
        }
        chapter_num = display_chapter_number(chapter.title, chapter.sort_order)
        for nc in req.new_characters:
            if not nc.name or nc.name in existing_names:
                continue  # 跳过重名
            tier = "emergent" if nc.arc_scope == "single_chapter" else "supporting"
            new_char = Character(
                project_id=project_id,
                name=nc.name,
                role=nc.role or "supporting",
                character_tier=tier,
                gender=nc.gender,
                age=nc.age,
                faction=nc.faction,
                personality=nc.personality,
                motivation=nc.motivation,
                background=nc.background,
                current_realm=nc.current_realm,
                current_status=nc.current_status or "alive",
                current_location=nc.current_location,
                author_notes=nc.author_notes,
                extra={"first_appearance_chapter": chapter_num, "arc_scope": nc.arc_scope},
            )
            db.add(new_char)
            existing_names.add(nc.name)
            added_new_characters.append(nc.name)

    # ── 保存作者备注到章节 ────────────────────────────
    if req.notes:
        memory = MemoryChunk(
            project_id=project_id,
            chapter_id=req.chapter_id,
            chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
            memory_type="event",
            title="章节复盘备注",
            content=req.notes.strip(),
            tags=["复盘备注"],
        )
        db.add(memory)
        _new_memory_chunks.append(memory)
        added_memories.append(memory.title)

    db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter.id,
    ).delete(synchronize_session=False)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(400, f"章节复盘提交失败：{exc.__class__.__name__}")

    # 异步向量化新增记忆（不阻塞响应）
    for mc in _new_memory_chunks:
        embed_text = f"{mc.title or ''}\n{mc.content}".strip()
        embed_chunk_async(mc.id, embed_text, SessionLocal)

    new_char_suffix = f"、新配角入库 {len(added_new_characters)} 个（{', '.join(added_new_characters)}）" if added_new_characters else ""
    return {
        "ok": True,
        "updated_characters": updated_chars,
        "updated_storylines": updated_storylines,
        "added_memories": added_memories,
        "added_new_characters": added_new_characters,
        "chapter_index_saved": chapter_index_saved,
        "chapter_index_error": chapter_index_error,
        "synced_foreshadows": synced_foreshadows,
        "asset_updates": asset_stats,
        "message": (
            f"已更新 {len(updated_chars)} 个人物状态、{len(updated_storylines)} 条故事线、"
            f"{len(added_memories)} 条记忆、章节索引={'已写入' if chapter_index_saved else '未更新'}、"
            f"伏笔管理新增{synced_foreshadows['created']}条/更新{synced_foreshadows['updated']}条/"
            f"回收{synced_foreshadows['resolved']}条、资产新增"
            f"{asset_stats['created_items'] + asset_stats['created_skills'] + asset_stats['created_factions']}条/"
            f"更新{asset_stats['updated_items'] + asset_stats['updated_skills'] + asset_stats['updated_factions']}条"
            f"{new_char_suffix}"
        ),
    }


# ── 自动复盘提取（AI 读章节 → 建议人物/故事线更新）────────
class AutoDebriefRequest(BaseModel):
    chapter_id: str
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None
    force_refresh: bool = False


def _chapter_debrief_content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

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
    narrative_plain, _ = split_plain_manuscript_and_index_block(plain_content)
    if not narrative_plain.strip():
        narrative_plain = plain_content.strip()
    content_hash = _chapter_debrief_content_hash(narrative_plain)
    current_llm_provider = str(req.llm_provider_id) if req.llm_provider_id else None

    cached = db.query(ChapterDebriefCache).filter(
        ChapterDebriefCache.project_id == project_id,
        ChapterDebriefCache.chapter_id == chapter.id,
    ).first()
    if (
        cached
        and not req.force_refresh
        and cached.content_hash == content_hash
        and cached.model_profile == req.model_profile
        and (cached.llm_provider_id or None) == current_llm_provider
        and isinstance(cached.payload, dict)
    ):
        payload = dict(cached.payload)
        payload["cached"] = True
        return payload

    result = await svc.auto_extract_debrief(
        chapter_content=narrative_plain,
        chapter_title=chapter.title,
        chapter_number=display_chapter_number(chapter.title, chapter.sort_order),
        character_states=character_states,
        storylines=storylines_data,
    )
    if isinstance(result, dict) and not result.get("error"):
        if not cached:
            cached = ChapterDebriefCache(
                project_id=project_id,
                chapter_id=chapter.id,
            )
            db.add(cached)
        cached.content_hash = content_hash
        cached.model_profile = req.model_profile
        cached.llm_provider_id = current_llm_provider
        cached.payload = result
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
    result["cached"] = False
    return result


# ── 记忆库查询 ────────────────────────────────────────
@router.get("/memory", response_model=List[MemoryChunkOut])
def list_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    q = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
    )
    if memory_type:
        q = q.filter(MemoryChunk.memory_type == memory_type)
    return q.order_by(
        func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc(),
        MemoryChunk.created_at,
    ).all()
