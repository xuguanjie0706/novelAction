import re
from typing import Optional

from sqlalchemy import asc, desc, nullslast
from sqlalchemy.orm import Session

from app.models import Chapter, Foreshadow
from app.routers.ai.schemas import ChapterIndexPayload
from app.utils.chapter_numbering import display_chapter_number

# 中文与 F 之间没有空格时，`\b` 词边界不成立，会导致「回收F-003」类文本漏提编号。
# 末尾 `(?![0-9\-_])` 确保 `F-020-01` / `F-020_2` 这类 AI 自创的"子编号"格式
# 不会被截取出父编号 `F-020` 而错走 update 分支（详见 2026-05-07 修复记录）。
_F_CODE_IN_PROSE_RE = re.compile(
    r"(?<![A-Za-z0-9_])F[-_ ]?(\d{1,4})(?![0-9\-_])",
    flags=re.IGNORECASE,
)

# 描述前缀清洗用：允许可选的 `-NN` / `_NN` 子编号一并剥离，
# 避免 `F-020-01：xxx` 经过清洗后残留成 `01：xxx`。
_F_CODE_DESC_PREFIX_RE = re.compile(
    r"^\s*F[-_ ]?\d{1,4}(?:[-_]\d{1,4})?\s*[:：\-—]\s*",
    flags=re.IGNORECASE,
)


def existing_foreshadow_codes(db: Session, project_id: str) -> set[str]:
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


def next_foreshadow_code(db: Session, project_id: str, reserved_codes: Optional[set[str]] = None) -> str:
    used_codes = existing_foreshadow_codes(db, project_id)
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


def foreshadow_payload_from_index_item(item: dict, default_status: str = "open") -> Optional[dict]:
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

    # 优先读显式 code 字段（新格式，_split_foreshadow_updates 已规范化为 F-NNN）；
    # 仅当显式字段缺失时，才从 description 文本中用正则提取（兼容旧缓存/手动编辑路径）。
    explicit_code = item.get("code")
    if explicit_code and str(explicit_code).strip():
        m = _F_CODE_IN_PROSE_RE.search(str(explicit_code).strip())
        code = f"F-{int(m.group(1)):03d}" if m else None
    else:
        code = None
        code_match = _F_CODE_IN_PROSE_RE.search(text)
        if code_match:
            code = f"F-{int(code_match.group(1)):03d}"

    description = _F_CODE_DESC_PREFIX_RE.sub("", text).strip()
    description = description or text

    # planned_action：新格式中 _split_foreshadow_updates 已按 action 字段赋值；
    # 旧格式走原有逻辑（文本推断）兜底。
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


def _normalize_f_code(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    m = _F_CODE_IN_PROSE_RE.search(str(raw).strip())
    return f"F-{int(m.group(1)):03d}" if m else None


def pick_open_foreshadow_for_resolve(open_rows: list[Foreshadow], payload: dict) -> Optional[Foreshadow]:
    """在无 F 编号时，将复盘条目与仍为 open 的全局伏笔对齐（跨章回收）。"""
    if not open_rows or not payload:
        return None
    desc = (payload.get("description") or "").strip()
    blob = " ".join(
        x for x in (desc, (payload.get("title") or "").strip()) if x
    )
    if blob:
        want = _normalize_f_code(blob)
        if want:
            for f in open_rows:
                got = _normalize_f_code(f.code)
                if got and got == want:
                    return f
    title = (payload.get("title") or "").strip()
    if title:
        for f in open_rows:
            if (f.title or "").strip() == title:
                return f
    if not desc:
        return None
    for f in open_rows:
        ft = (f.title or "").strip()
        if len(ft) >= 4 and ft in desc:
            return f
        fd = (f.description or "").strip()
        if len(fd) >= 12 and fd[:120] in desc:
            return f
    return None


def sync_chapter_index_foreshadows(
    db: Session,
    project_id: str,
    chapter: Chapter,
    chapter_index: ChapterIndexPayload,
) -> dict:
    """Mirror actual chapter-index foreshadows into the global tracking table."""
    stats = {"created": 0, "updated": 0, "resolved": 0}
    chapter_number = display_chapter_number(chapter.title, chapter.sort_order)
    reserved_codes: set[str] = set()

    def find_existing_laid(payload: dict) -> Optional[Foreshadow]:
        q = db.query(Foreshadow).filter(Foreshadow.project_id == project_id)
        if payload.get("code"):
            existing = q.filter(Foreshadow.code == payload["code"]).first()
            if existing:
                return existing
        return q.filter(
            Foreshadow.title == payload["title"],
            Foreshadow.laid_chapter_id == chapter.id,
        ).first()

    def find_existing_resolve(payload: dict) -> Optional[Foreshadow]:
        q = db.query(Foreshadow).filter(Foreshadow.project_id == project_id)
        if payload.get("code"):
            existing = q.filter(Foreshadow.code == payload["code"]).first()
            if existing:
                return existing
        open_rows = (
            q.filter(Foreshadow.status == "open")
            .order_by(desc(Foreshadow.priority), nullslast(asc(Foreshadow.laid_chapter_number)))
            .all()
        )
        return pick_open_foreshadow_for_resolve(open_rows, payload)

    for item in chapter_index.actual_foreshadows_laid or []:
        payload = foreshadow_payload_from_index_item(item, default_status="open")
        if not payload:
            continue
        existing = find_existing_laid(payload)
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

        code = payload["code"] or next_foreshadow_code(db, project_id, reserved_codes)
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
        payload = foreshadow_payload_from_index_item(item, default_status="resolved")
        if not payload:
            continue
        existing = find_existing_resolve(payload)
        if existing:
            existing.status = "resolved"
            existing.resolved_chapter_id = chapter.id
            existing.resolved_chapter_number = chapter_number
            if payload.get("description"):
                existing.description = payload["description"]
            stats["resolved"] += 1
            continue

        code = payload["code"] or next_foreshadow_code(db, project_id, reserved_codes)
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
