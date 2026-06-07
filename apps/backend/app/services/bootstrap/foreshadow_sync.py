"""章纲伏笔 → Foreshadow 表同步。

优先读 ``extra.foreshadow_ops`` 结构化数组；无 ops 时回退解析 ``extra.foreshadow`` 文本 DSL。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.services.bootstrap.foreshadow_ops import (
    coerce_foreshadow_ops,
    legacy_string_to_ops,
    normalize_op,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 向后兼容：测试与 foreshadow_schedule_lock 仍从此处导入正则
from app.services.bootstrap.foreshadow_ops import (  # noqa: F401
    _RE_HEAT,
    _RE_LAY,
    _RE_RESOLVE,
    legacy_string_to_ops as _legacy_string_to_ops,
)


def _title_from_text(text: str, *, max_len: int = 200) -> str:
    """Foreshadow.title 必填；从描述/关键词截取可读标题。"""
    t = (text or "").strip()
    if not t:
        return "伏笔"
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def sync_chapter_foreshadow(
    db: "Session",
    project_id,
    outline_node,
    chapter_number: int,
) -> None:
    """解析章纲伏笔并同步 Foreshadow 表（幂等）。"""
    extra = outline_node.extra if isinstance(outline_node.extra, dict) else {}
    ops = extra.get("foreshadow_ops")
    if isinstance(ops, list) and ops:
        normalized = [o for o in (normalize_op(x) for x in ops) if o]
    else:
        raw = (extra.get("foreshadow") or "").strip()
        normalized = legacy_string_to_ops(raw) if raw else []

    if not normalized:
        return

    try:
        _do_sync_from_ops(db, project_id, outline_node, chapter_number, normalized)
    except Exception:
        logger.exception(
            "伏笔同步失败（项目=%s，章=%d），已跳过", project_id, chapter_number
        )


def _keywords_overlap(a: str, b: str, *, min_window: int = 4) -> bool:
    """判断两段中文是否指向同一伏笔。

    短名称（≤8 字）允许 2 字片段匹配；较长文本要求 ≥min_window 字，避免「真相」等泛词误关联。
    """
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    short_mode = max(len(a), len(b)) <= 8
    sub_min = 2 if short_mode else min_window
    if len(a) >= sub_min and a in b:
        return True
    if len(b) >= sub_min and b in a:
        return True
    step = 1 if short_mode else 1
    frag_len = 2 if short_mode else min_window
    if len(a) >= frag_len:
        for i in range(0, len(a) - frag_len + 1, step):
            if a[i : i + frag_len] in b:
                return True
    return False


def _core_mystery_names(db, project_id) -> list[str]:
    from app.models import Project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return []
    extra = project.extra if isinstance(project.extra, dict) else {}
    mysteries = extra.get("core_mysteries") or []
    return [
        (m.get("name") or "").strip()
        for m in mysteries
        if isinstance(m, dict) and (m.get("name") or "").strip()
    ]


def _find_existing_for_lay(db, project_id, content: str):
    from app.models import Foreshadow

    content = content.strip()
    if not content:
        return None

    exact = (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.description == content,
        )
        .first()
    )
    if exact:
        return exact

    active_rows = (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status.in_(["planned", "open"]),
        )
        .all()
    )
    for fs in active_rows:
        title = (fs.title or "").strip()
        if title and _keywords_overlap(content, title):
            return fs
        extra = fs.extra if isinstance(fs.extra, dict) else {}
        mystery_name = (extra.get("mystery_name") or "").strip()
        if mystery_name and _keywords_overlap(content, mystery_name):
            return fs

    for name in _core_mystery_names(db, project_id):
        if _keywords_overlap(content, name):
            for fs in active_rows:
                extra = fs.extra if isinstance(fs.extra, dict) else {}
                mn = (extra.get("mystery_name") or fs.title or "").strip()
                if _keywords_overlap(name, mn) or _keywords_overlap(content, mn):
                    return fs
    return None


def _link_lay_to_existing(fs, outline_node, chapter_number: int, theme_note: str) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    extra = dict(fs.extra or {})
    extra["source_outline_node_id"] = str(outline_node.id)
    if theme_note:
        extra["theme_note"] = theme_note

    planned = extra.get("planned_lay_chapter")
    if planned is None and extra.get("is_core_mystery"):
        planned = fs.laid_chapter_number
    try:
        planned_int = int(planned) if planned else None
    except (TypeError, ValueError):
        planned_int = None

    if extra.get("is_core_mystery") and planned_int and chapter_number < planned_int:
        fs.extra = extra
        flag_modified(fs, "extra")
        logger.debug(
            "伏笔[埋·关联] chapter=%d 早于计划第%d章，仅关联不更新埋设章",
            chapter_number,
            planned_int,
        )
        return

    # 核心谜题：章纲同步不得把「实际埋下章」推后到更晚章节（常见于关键词误匹配）
    if extra.get("is_core_mystery"):
        prior = extra.get("actually_laid_chapter") or fs.laid_chapter_number
        try:
            prior_int = int(prior) if prior is not None else None
        except (TypeError, ValueError):
            prior_int = None
        if prior_int is not None and chapter_number > prior_int:
            fs.extra = extra
            flag_modified(fs, "extra")
            logger.debug(
                "伏笔[埋·关联] chapter=%d 晚于已记录第%d章，跳过覆盖埋设章",
                chapter_number,
                prior_int,
            )
            return
        if planned_int and chapter_number > planned_int + 2:
            fs.extra = extra
            flag_modified(fs, "extra")
            logger.debug(
                "伏笔[埋·关联] chapter=%d 远超计划第%d章，跳过覆盖埋设章",
                chapter_number,
                planned_int,
            )
            return

    if not fs.laid_chapter_id:
        fs.laid_chapter_number = chapter_number
        extra["actually_laid_chapter"] = chapter_number
    fs.extra = extra
    flag_modified(fs, "extra")
    logger.debug("伏笔[埋·关联] chapter=%d title=%s", chapter_number, (fs.title or "")[:30])


def _find_by_code(db, project_id, code: str):
    from app.models import Foreshadow

    code = (code or "").strip()
    if not code:
        return None
    return (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.code == code,
            Foreshadow.status.in_(["planned", "open"]),
        )
        .first()
    )


def _find_foreshadow(db, project_id, keyword: str):
    """按 code 精确匹配，再按 description 模糊匹配。"""
    from app.models import Foreshadow

    kw = (keyword or "").strip()
    if not kw:
        return None

    by_code = _find_by_code(db, project_id, kw)
    if by_code:
        return by_code

    frag = kw[:20]
    return (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status.in_(["planned", "open"]),
            Foreshadow.description.contains(frag),
        )
        .first()
    )


def _resolve_foreshadow_ref(db, project_id, op: dict[str, Any]):
    """heat/resolve：优先 code，再 note/name 模糊匹配。"""
    if op.get("code"):
        fs = _find_by_code(db, project_id, op["code"])
        if fs:
            return fs
    for key in ("note", "name"):
        val = (op.get(key) or "").strip()
        if val:
            fs = _find_foreshadow(db, project_id, val)
            if fs:
                return fs
    return None


def _do_sync_from_ops(
    db,
    project_id,
    outline_node,
    chapter_number: int,
    ops: list[dict[str, Any]],
) -> None:
    from app.models import Foreshadow
    from sqlalchemy.orm.attributes import flag_modified

    for raw in ops:
        op = normalize_op(raw)
        if not op:
            continue

        if op["op"] == "lay":
            content = op["name"]
            theme_note = op.get("theme") or ""
            existing = _find_existing_for_lay(db, project_id, content)
            if existing:
                _link_lay_to_existing(existing, outline_node, chapter_number, theme_note)
                continue
            fs = Foreshadow(
                project_id=project_id,
                title=_title_from_text(content),
                description=content,
                laid_chapter_number=chapter_number,
                status="planned",
                foreshadow_type="hook",
                extra={
                    "theme_note": theme_note,
                    "source_outline_node_id": str(outline_node.id),
                    "heat_log": [],
                },
            )
            db.add(fs)
            logger.debug("伏笔[埋·planned] chapter=%d content=%s", chapter_number, content[:30])
            continue

        if op["op"] == "heat":
            fs = _resolve_foreshadow_ref(db, project_id, op)
            if fs:
                extra = dict(fs.extra or {})
                heat_log = list(extra.get("heat_log") or [])
                heat_log.append({
                    "chapter": chapter_number,
                    "note": op.get("note") or op.get("code") or op.get("name") or "",
                })
                extra["heat_log"] = heat_log
                fs.extra = extra
                flag_modified(fs, "extra")
                logger.debug(
                    "伏笔[加热] chapter=%d ref=%s",
                    chapter_number,
                    (op.get("code") or op.get("note") or "")[:30],
                )
            continue

        if op["op"] == "resolve":
            fs = _resolve_foreshadow_ref(db, project_id, op)
            if fs and fs.status in ("planned", "open"):
                if not fs.planned_resolve_chapter:
                    fs.planned_resolve_chapter = chapter_number
                    fs.planned_action = "resolve"
                logger.debug(
                    "伏笔[收·规划] chapter=%d ref=%s",
                    chapter_number,
                    (op.get("code") or op.get("note") or "")[:30],
                )

    db.flush()
