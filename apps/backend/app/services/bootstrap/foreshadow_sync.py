"""章纲伏笔字段 → Foreshadow 表双向同步工具。

格式约定（与 vol1/vol_chapter_plans prompt 一致）：
  埋[伏笔内容|主题:关联说明]   → 创建 Foreshadow(status=planned)【规划意图，非权威状态】
  加热[伏笔代号+推进方式]      → 在已有记录的 extra.heat_log 追加
  收[伏笔代号+内容]            → 更新 planned_resolve_chapter，不改 status【实际回收由复盘确认】

权威链：章纲 sync → status=planned（规划）；复盘 sync → status=open/resolved（确认）。
禁止在本文件中将任何记录升格为 open/resolved，那是复盘路径的专属权限。

使用方式：
  在章纲落库循环体内，每章节落库后调用：
    sync_chapter_foreshadow(db, project_id, outline_node, chapter_number)
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 匹配三种操作符（允许全角/半角方括号）
_RE_LAY = re.compile(r"埋[[\[＜](.+?)[)\]＞]", re.UNICODE)
_RE_HEAT = re.compile(r"加热[[\[＜](.+?)[)\]＞]", re.UNICODE)
_RE_RESOLVE = re.compile(r"收[[\[＜](.+?)[)\]＞]", re.UNICODE)

# 解析"伏笔内容|主题:关联"格式，分离名称与主题注释
_RE_THEME = re.compile(r"^(.+?)\|主题[:：](.+)$")


def _parse_lay(raw: str) -> tuple[str, str]:
    """从 '伏笔内容|主题:关联' 解析出 (content, theme_note)。"""
    m = _RE_THEME.match(raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), ""


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
    """解析 outline_node.extra['foreshadow'] 并同步 Foreshadow 表。

    幂等设计：同一章节多次调用时，description 相同的埋伏笔不重复创建。

    Args:
        db:             SQLAlchemy Session。
        project_id:     项目 UUID。
        outline_node:   已落库的 OutlineNode（chapter_plan 类型）。
        chapter_number: 本章在全书中的章号（1-based）。
    """
    from app.models import Foreshadow

    raw = (outline_node.extra or {}).get("foreshadow", "")
    if not raw:
        return

    try:
        _do_sync(db, project_id, outline_node, chapter_number, raw)
    except Exception:
        logger.exception(
            "伏笔同步失败（项目=%s，章=%d），已跳过", project_id, chapter_number
        )


def _keywords_overlap(a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    for i in range(len(a) - 1):
        if a[i : i + 2] in b:
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


def _find_existing_for_lay(db, project_id, content: str) -> "Foreshadow | None":
    """匹配已有伏笔（核心谜题 / 标题 / 描述），避免章纲 sync 重复建 F-xxx。

    同时搜索 planned / open 状态（复盘确认的 open 也是同一条伏笔的升格版，不应重建）。
    """
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

    # planned + open 都视为"已有"，避免章纲二次展开时重复建档
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
            matched = (
                db.query(Foreshadow)
                .filter(
                    Foreshadow.project_id == project_id,
                    Foreshadow.status.in_(["planned", "open"]),
                )
                .all()
            )
            for fs in matched:
                extra = fs.extra if isinstance(fs.extra, dict) else {}
                mn = (extra.get("mystery_name") or fs.title or "").strip()
                if _keywords_overlap(name, mn) or _keywords_overlap(content, mn):
                    return fs
    return None


def _link_lay_to_existing(fs, outline_node, chapter_number: int, theme_note: str) -> None:
    """将章纲「埋」关联到已有台账，仅在到达计划章或普通伏笔时写入实际埋设章。"""
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

    if not fs.laid_chapter_id:
        fs.laid_chapter_number = chapter_number
        extra["actually_laid_chapter"] = chapter_number
    fs.extra = extra
    flag_modified(fs, "extra")
    logger.debug("伏笔[埋·关联] chapter=%d title=%s", chapter_number, (fs.title or "")[:30])


def _do_sync(db, project_id, outline_node, chapter_number: int, raw: str) -> None:
    from app.models import Foreshadow

    # ── 埋 ────────────────────────────────────────────────────────────────
    for m in _RE_LAY.finditer(raw):
        content, theme_note = _parse_lay(m.group(1))
        if not content:
            continue
        existing = _find_existing_for_lay(db, project_id, content)
        if existing:
            _link_lay_to_existing(existing, outline_node, chapter_number, theme_note)
            continue
        fs = Foreshadow(
            project_id=project_id,
            title=_title_from_text(content),
            description=content,
            laid_chapter_number=chapter_number,
            status="planned",   # 章纲规划意图；复盘确认后由 sync_chapter_index_foreshadows 升为 open
            foreshadow_type="hook",
            extra={
                "theme_note": theme_note,
                "source_outline_node_id": str(outline_node.id),
                "heat_log": [],
            },
        )
        db.add(fs)
        logger.debug("伏笔[埋·planned] chapter=%d content=%s", chapter_number, content[:30])

    # ── 加热 ──────────────────────────────────────────────────────────────
    for m in _RE_HEAT.finditer(raw):
        keyword = m.group(1).strip()
        if not keyword:
            continue
        # 按 description 模糊匹配已有 open 伏笔
        fs = _find_foreshadow(db, project_id, keyword)
        if fs:
            from sqlalchemy.orm.attributes import flag_modified

            extra = dict(fs.extra or {})
            heat_log = list(extra.get("heat_log") or [])
            heat_log.append({"chapter": chapter_number, "note": keyword})
            extra["heat_log"] = heat_log
            fs.extra = extra
            flag_modified(fs, "extra")
            logger.debug("伏笔[加热] chapter=%d keyword=%s", chapter_number, keyword[:30])

    # ── 收（章纲规划，只更新预计回收章，不改 status） ────────────────────
    # 实际 status=resolved 只能由复盘路径（sync_chapter_index_foreshadows）写入，
    # 章纲的「收」仅代表"计划在此章回收"的意图。
    for m in _RE_RESOLVE.finditer(raw):
        keyword = m.group(1).strip()
        if not keyword:
            continue
        fs = _find_foreshadow(db, project_id, keyword)
        if fs and fs.status in ("planned", "open"):
            if not fs.planned_resolve_chapter:
                fs.planned_resolve_chapter = chapter_number
                fs.planned_action = "resolve"
            logger.debug("伏笔[收·规划] chapter=%d keyword=%s", chapter_number, keyword[:30])

    db.flush()  # 不 commit，由调用方统一提交


def _find_foreshadow(db, project_id, keyword: str):
    """按关键词模糊匹配 planned/open 伏笔记录（description LIKE %keyword%）。"""
    from app.models import Foreshadow

    # 取关键词前20字做 LIKE 查询，避免过长导致无结果
    kw = keyword[:20]
    return (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status.in_(["planned", "open"]),
            Foreshadow.description.contains(kw),
        )
        .first()
    )
