"""章纲伏笔字段 → Foreshadow 表双向同步工具。

格式约定（与 vol1/vol_chapter_plans prompt 一致）：
  埋[伏笔内容|主题:关联说明]   → 创建 Foreshadow(status=open)
  加热[伏笔代号+推进方式]      → 在已有记录的 extra.heat_log 追加
  收[伏笔代号+内容]            → 更新已有记录 status=resolved

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


def _do_sync(db, project_id, outline_node, chapter_number: int, raw: str) -> None:
    from app.models import Foreshadow

    # ── 埋 ────────────────────────────────────────────────────────────────
    for m in _RE_LAY.finditer(raw):
        content, theme_note = _parse_lay(m.group(1))
        if not content:
            continue
        # 幂等：同项目同 description 已存在则跳过
        exists = (
            db.query(Foreshadow)
            .filter(
                Foreshadow.project_id == project_id,
                Foreshadow.description == content,
            )
            .first()
        )
        if exists:
            continue
        fs = Foreshadow(
            project_id=project_id,
            description=content,
            laid_chapter_number=chapter_number,
            status="open",
            foreshadow_type="hook",
            extra={
                "theme_note": theme_note,
                "source_outline_node_id": str(outline_node.id),
                "heat_log": [],
            },
        )
        db.add(fs)
        logger.debug("伏笔[埋] chapter=%d content=%s", chapter_number, content[:30])

    # ── 加热 ──────────────────────────────────────────────────────────────
    for m in _RE_HEAT.finditer(raw):
        keyword = m.group(1).strip()
        if not keyword:
            continue
        # 按 description 模糊匹配已有 open 伏笔
        fs = _find_foreshadow(db, project_id, keyword)
        if fs:
            extra = dict(fs.extra or {})
            heat_log = list(extra.get("heat_log") or [])
            heat_log.append({"chapter": chapter_number, "note": keyword})
            extra["heat_log"] = heat_log
            fs.extra = extra
            logger.debug("伏笔[加热] chapter=%d keyword=%s", chapter_number, keyword[:30])

    # ── 收 ────────────────────────────────────────────────────────────────
    for m in _RE_RESOLVE.finditer(raw):
        keyword = m.group(1).strip()
        if not keyword:
            continue
        fs = _find_foreshadow(db, project_id, keyword)
        if fs and fs.status == "open":
            fs.status = "resolved"
            fs.resolved_chapter_number = chapter_number
            logger.debug("伏笔[收] chapter=%d keyword=%s", chapter_number, keyword[:30])

    db.flush()  # 不 commit，由调用方统一提交


def _find_foreshadow(db, project_id, keyword: str):
    """按关键词模糊匹配 open 伏笔记录（description LIKE %keyword%）。"""
    from app.models import Foreshadow

    # 取关键词前20字做 LIKE 查询，避免过长导致无结果
    kw = keyword[:20]
    return (
        db.query(Foreshadow)
        .filter(
            Foreshadow.project_id == project_id,
            Foreshadow.status == "open",
            Foreshadow.description.contains(kw),
        )
        .first()
    )
