"""首页 Dashboard 聚合接口。

为创作端 ProjectsPage（首页）提供单一聚合数据：
- 写作统计（总字数 / 今日 / 连续天数 / 本周柱状图 / 写作天数 / 平均字数）
- 最近编辑章节列表（含完整 Project 用于跳转）
- 问候语用户名

设计原则
--------
- 写作量统计基于 ChapterVersion 快照增量计算（同章前后两次快照 word_count 差），
  这是当前唯一稳定的「人工/AI 实际写作行为」时序信号；纯 Chapter.updated_at
  会被复盘等后台动作误触发为「写作」。
- 章节缺失 ChapterVersion 的情况下统计偏低，但 total_words 仍取自 Chapter.word_count
  保持准确；这是已知妥协，迁移到「每日字数表」是后续扩展点。
- 时区：当前以服务器时区分桶。前端展示按浏览器本地时区拼日期，可在后续按
  `X-Tz-Offset` header 做服务端切换。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Chapter, ChapterIndex, ChapterVersion, Project
from app.models.user import User
from app.schemas.project import ProjectOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# 七天柱状图的星期标签（周一为 0）
_WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]
# 柱状图最小可见高度（像素），与前端 78px 满高保持比例
_BAR_MAX_PX = 78
_BAR_MIN_PX = 4


def compute_weekly_writing_stats(
    version_rows: Iterable[Tuple[Any, Optional[datetime], Optional[int]]],
    today: date,
) -> Dict[str, Any]:
    """从 ChapterVersion 快照原始三元组计算写作统计（纯函数，便于测试）。

    Args:
        version_rows: 形如 ``(chapter_id, created_at, word_count)`` 的迭代器，
            来自 ``db.query(ChapterVersion.chapter_id, ChapterVersion.created_at,
            ChapterVersion.word_count).filter(...)``。顺序无要求，函数内会按
            chapter_id+created_at 升序整理后再做差分。
        today: 用于划分「今天 / 本周（最近 7 天含今天） / 连续天数」的基准日期，
            通常传 ``datetime.now().date()``；测试可传固定值。

    Returns:
        dict，包含：

        - ``today_words``：今天的增量字数总和（int）。
        - ``streak_days``：从 today 起向前连续有写作的自然日数；today 没写为 0。
        - ``writing_days``：最近 7 天里 ``words > 0`` 的天数。
        - ``average_words``：最近 7 天总字数 / writing_days，向下取整；
          ``writing_days == 0`` 时为 0。
        - ``week``：长度 7 的列表，从 ``today - 6`` 到 ``today``，每项
          ``{date, weekday_label, words, height}``。
    """
    # ── 1. 把同章节的快照按时间升序，做差分得到「该快照新增字数」──
    #    同一章节首次出现时取 word_count 视为「从 0 写到当前」。
    grouped: Dict[Any, List[Tuple[datetime, int]]] = defaultdict(list)
    for chapter_id, created_at, word_count in version_rows:
        if created_at is None or word_count is None or chapter_id is None:
            continue
        grouped[chapter_id].append((created_at, int(word_count)))

    daily_words: Dict[date, int] = defaultdict(int)
    for snaps in grouped.values():
        snaps.sort(key=lambda x: x[0])
        prev_wc = 0
        for created_at, wc in snaps:
            delta = wc - prev_wc
            if delta < 0:
                # 删字段不计入「写了多少字」，但保留 prev_wc 推进，避免下一次又用旧值算正差
                delta = 0
            prev_wc = wc
            day = _to_local_date(created_at)
            daily_words[day] += delta

    # ── 2. 七天柱状图：从 today-6 到 today ──
    week: List[Dict[str, Any]] = []
    week_total_words = 0
    week_max_words = 0
    week_writing_days = 0
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        words = int(daily_words.get(day, 0))
        week_total_words += words
        if words > 0:
            week_writing_days += 1
        if words > week_max_words:
            week_max_words = words
        week.append({
            "date": day.isoformat(),
            "weekday_label": _WEEKDAY_LABELS[day.weekday()],
            "words": words,
            # height 在第二轮统一规整（需要 week_max_words）
            "height": 0,
        })

    # 高度按全周最大值归一到 [_BAR_MIN_PX, _BAR_MAX_PX]
    for item in week:
        if week_max_words <= 0:
            item["height"] = _BAR_MIN_PX
        else:
            ratio = item["words"] / week_max_words
            item["height"] = max(int(round(ratio * _BAR_MAX_PX)), _BAR_MIN_PX)

    # ── 3. 连续创作天数：从 today 向前数 ──
    streak = 0
    cursor = today
    while daily_words.get(cursor, 0) > 0:
        streak += 1
        cursor = cursor - timedelta(days=1)

    average = (week_total_words // week_writing_days) if week_writing_days else 0

    return {
        "today_words": int(daily_words.get(today, 0)),
        "streak_days": int(streak),
        "writing_days": int(week_writing_days),
        "average_words": int(average),
        "week": week,
    }


def _to_local_date(dt: datetime) -> date:
    """统一把 timezone-aware / naive datetime 折算到「服务器本地日期」。

    数据库写入时一般带 UTC 时区；这里转到本机时区再取 ``.date()``，避免
    UTC 跨日凌晨数据被错算到「明天」。
    """
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone().date()


def _build_chapter_label(sort_order: int, title: str, chapter_number: Optional[int]) -> str:
    """组装「第 N 章 标题」展示文本，优先用 ChapterIndex.chapter_number。"""
    n = chapter_number if (chapter_number and chapter_number > 0) else (int(sort_order or 0) + 1)
    title = (title or "").strip()
    return f"第{n}章 {title}" if title else f"第{n}章"


@router.get("/home")
def get_home_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """首页所需的全量聚合数据。

    Returns:
        - greeting_name: 用户 username 优先，回退 email 前缀，再回退「写作者」
        - total_words: 当前用户名下未删章节的 ``word_count`` 总和
        - today_words / streak_days / writing_days / average_words / week:
          见 :func:`compute_weekly_writing_stats`
        - recent_chapters: 最近 5 个章节，按 ``Chapter.updated_at`` 降序，
          含完整 Project 对象（前端跳转需要）
    """
    today = datetime.now().date()

    # 当前用户名下未删章节字数总和（一次 SQL 聚合，避免拉全部 Chapter 行）
    total_words = (
        db.query(sa_func.coalesce(sa_func.sum(Chapter.word_count), 0))
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == current_user.id, Chapter.deleted_at.is_(None))
        .scalar()
    ) or 0

    # ChapterVersion 快照三元组（仅本用户）
    version_rows = (
        db.query(ChapterVersion.chapter_id, ChapterVersion.created_at, ChapterVersion.word_count)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == current_user.id)
        .all()
    )
    weekly = compute_weekly_writing_stats(version_rows, today)

    # 最近编辑章节
    recent_rows = (
        db.query(Chapter, Project)
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == current_user.id, Chapter.deleted_at.is_(None))
        .order_by(Chapter.updated_at.desc().nullslast())
        .limit(5)
        .all()
    )

    # 一次性取 ChapterIndex.chapter_number 用于章号优化（避免 N 次查询）
    recent_chapter_ids = [str(ch.id) for ch, _ in recent_rows]
    chapter_numbers: Dict[str, int] = {}
    if recent_chapter_ids:
        for ci in (
            db.query(ChapterIndex.chapter_id, ChapterIndex.chapter_number)
            .filter(ChapterIndex.chapter_id.in_(recent_chapter_ids))
            .all()
        ):
            chapter_numbers[str(ci.chapter_id)] = int(ci.chapter_number or 0)

    recent_chapters: List[Dict[str, Any]] = []
    for chapter, project in recent_rows:
        cnum = chapter_numbers.get(str(chapter.id))
        recent_chapters.append({
            "id": str(chapter.id),
            "title": chapter.title,
            "word_count": int(chapter.word_count or 0),
            "sort_order": int(chapter.sort_order or 0),
            "chapter_label": _build_chapter_label(chapter.sort_order or 0, chapter.title, cnum),
            "updated_at": chapter.updated_at.isoformat() if chapter.updated_at else None,
            "project": ProjectOut.model_validate(project).model_dump(mode="json"),
        })

    greeting_name = (
        (current_user.username or "").strip()
        or (current_user.email or "").split("@", 1)[0]
        or "写作者"
    )

    return {
        "greeting_name": greeting_name,
        "total_words": int(total_words),
        **weekly,
        "recent_chapters": recent_chapters,
    }
