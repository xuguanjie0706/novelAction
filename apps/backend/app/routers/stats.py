"""数据统计聚合接口。

为创作端 StatsPage 提供全量写作统计数据，涵盖：
- 全局 KPI：总字数、总作品数、总章节数、连续创作天数、今日字数、平均质检分
- 30 天字数趋势（按天分桶）
- 作品进度列表（含单本目标/实际/质检分）
- 题材 & 状态分布
- 写作习惯热力图（按星期分布）
- AI 生成统计（Bootstrap 次数、AI 调用总 token）
- 质检概览（平均分、欠债分布）

设计约定
--------
- 全部统计限定到 current_user，无跨用户数据泄露风险。
- 时区：服务器本地时区分桶，与 dashboard.py 保持一致。
- 性能：除 30 天趋势的 ChapterVersion 差分外，其余均为单次 SQL 聚合，无 N+1。
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Chapter, ChapterVersion, Project
from app.models.bootstrap_run import BootstrapRun
from app.models.llm_call_log import LlmCallLog
from app.models.quality_debt import QualityDebt
from app.models.user import User

router = APIRouter(prefix="/stats", tags=["stats"])


# ──────────────────────────────────────────────
# 内部工具函数
# ──────────────────────────────────────────────

def _to_local_date(dt: datetime) -> date:
    """将 timezone-aware 或 naive datetime 转换为服务器本地日期。"""
    if dt is None:
        return date.today()
    if dt.tzinfo is None:
        return dt.date()
    return dt.astimezone().date()


def _build_30day_trend(
    version_rows: List[Tuple[Any, Optional[datetime], Optional[int]]],
    today: date,
) -> List[Dict[str, Any]]:
    """对 ChapterVersion 快照做差分，得到近 30 天每日字数增量。

    Args:
        version_rows: (chapter_id, created_at, word_count) 三元组列表。
        today: 统计基准日期。

    Returns:
        长度 30 的列表，从 today-29 到 today，每项含 date / words / weekday_label。
    """
    _WD = ["一", "二", "三", "四", "五", "六", "日"]

    # 按章分组，时间升序差分
    grouped: Dict[Any, List[Tuple[datetime, int]]] = defaultdict(list)
    for chapter_id, created_at, word_count in version_rows:
        if chapter_id is None or created_at is None or word_count is None:
            continue
        grouped[chapter_id].append((created_at, int(word_count)))

    daily: Dict[date, int] = defaultdict(int)
    for snaps in grouped.values():
        snaps.sort(key=lambda x: x[0])
        prev = 0
        for dt, wc in snaps:
            delta = max(0, wc - prev)
            prev = wc
            daily[_to_local_date(dt)] += delta

    result: List[Dict[str, Any]] = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        words = int(daily.get(day, 0))
        result.append({
            "date": day.isoformat(),
            "weekday_label": _WD[day.weekday()],
            "words": words,
        })
    return result


def _build_weekday_distribution(
    version_rows: List[Tuple[Any, Optional[datetime], Optional[int]]],
) -> List[Dict[str, Any]]:
    """统计各星期几的字数占比，用于「写作习惯」环图/柱图。

    Returns:
        长度 7 的列表，从周一到周日，含 weekday / label / words / pct。
    """
    _WD = ["一", "二", "三", "四", "五", "六", "日"]
    grouped: Dict[Any, List[Tuple[datetime, int]]] = defaultdict(list)
    for chapter_id, created_at, word_count in version_rows:
        if chapter_id is None or created_at is None or word_count is None:
            continue
        grouped[chapter_id].append((created_at, int(word_count)))

    wd_words: Dict[int, int] = defaultdict(int)
    for snaps in grouped.values():
        snaps.sort(key=lambda x: x[0])
        prev = 0
        for dt, wc in snaps:
            delta = max(0, wc - prev)
            prev = wc
            wd_words[_to_local_date(dt).weekday()] += delta

    total = sum(wd_words.values()) or 1
    return [
        {
            "weekday": i,
            "label": _WD[i],
            "words": int(wd_words.get(i, 0)),
            "pct": round(wd_words.get(i, 0) / total * 100, 1),
        }
        for i in range(7)
    ]


def _compute_streak(daily_words: Dict[date, int], today: date) -> int:
    """从 today 向前连续有写作的自然日数；today 没写为 0。"""
    streak = 0
    cursor = today
    while daily_words.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


# ──────────────────────────────────────────────
# 路由
# ──────────────────────────────────────────────

@router.get("/summary")
def get_stats_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """返回数据统计页全量聚合数据。

    Returns:
        dict，结构见下方各字段注释。

    Raises:
        无显式异常；内部错误交由 FastAPI 全局处理器捕获。
    """
    today = datetime.now().date()
    uid = current_user.id

    # ── 1. 作品基础聚合 ────────────────────────────────────
    projects_rows = (
        db.query(Project)
        .filter(Project.user_id == uid)
        .all()
    )
    total_projects = len(projects_rows)

    status_dist: Dict[str, int] = defaultdict(int)
    genre_dist: Dict[str, int] = defaultdict(int)
    for p in projects_rows:
        status_dist[p.status or "drafting"] += 1
        genre_dist[p.genre or "其他"] += 1

    # ── 2. 章节基础聚合 ────────────────────────────────────
    chapter_agg = (
        db.query(
            sa_func.count(Chapter.id).label("total"),
            sa_func.coalesce(sa_func.sum(Chapter.word_count), 0).label("total_words"),
            sa_func.coalesce(sa_func.avg(Chapter.last_quality_score), 0).label("avg_quality"),
        )
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == uid, Chapter.deleted_at.is_(None))
        .first()
    )
    total_chapters = int(chapter_agg.total or 0)
    total_words = int(chapter_agg.total_words or 0)
    avg_quality = round(float(chapter_agg.avg_quality or 0), 1)

    # ── 3. 30 天字数趋势（ChapterVersion 差分） ────────────
    cutoff = datetime.combine(today - timedelta(days=29), datetime.min.time())
    version_rows = (
        db.query(
            ChapterVersion.chapter_id,
            ChapterVersion.created_at,
            ChapterVersion.word_count,
        )
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == uid, ChapterVersion.created_at >= cutoff)
        .all()
    )
    trend_30 = _build_30day_trend(version_rows, today)

    # 今日字数、连续天数
    daily_sum: Dict[date, int] = defaultdict(int)
    for item in trend_30:
        d = date.fromisoformat(item["date"])
        daily_sum[d] += item["words"]
    today_words = int(daily_sum.get(today, 0))
    streak_days = _compute_streak(daily_sum, today)

    # ── 4. 近 90 天写作习惯（星期分布，需更长窗口） ────────
    cutoff_90 = datetime.combine(today - timedelta(days=89), datetime.min.time())
    version_rows_90 = (
        db.query(
            ChapterVersion.chapter_id,
            ChapterVersion.created_at,
            ChapterVersion.word_count,
        )
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .join(Project, Project.id == Chapter.project_id)
        .filter(Project.user_id == uid, ChapterVersion.created_at >= cutoff_90)
        .all()
    )
    weekday_dist = _build_weekday_distribution(version_rows_90)

    # 写作天数（30 天内有写作记录的自然日数）
    writing_days_30 = sum(1 for item in trend_30 if item["words"] > 0)

    # ── 5. 质检欠债 ────────────────────────────────────────
    debt_rows = (
        db.query(QualityDebt.severity, sa_func.count(QualityDebt.id))
        .join(Project, Project.id == QualityDebt.project_id)
        .filter(
            Project.user_id == uid,
            QualityDebt.status == "pending",
        )
        .group_by(QualityDebt.severity)
        .all()
    )
    debt_by_severity: Dict[str, int] = {row[0]: int(row[1]) for row in debt_rows}
    total_debts = sum(debt_by_severity.values())

    # ── 6. AI 生成统计 ─────────────────────────────────────
    bootstrap_count = (
        db.query(sa_func.count(BootstrapRun.id))
        .filter(BootstrapRun.user_id == uid, BootstrapRun.status == "done")
        .scalar()
    ) or 0

    # LLM 调用 token 统计（近 30 天）
    llm_token_agg = (
        db.query(
            sa_func.count(LlmCallLog.id).label("call_count"),
        )
        .filter(
            LlmCallLog.created_at >= cutoff,
            LlmCallLog.context["user_id"].as_string() == str(uid),
        )
        .first()
    )
    ai_call_count_30 = int(llm_token_agg.call_count if llm_token_agg else 0)

    # ── 7. 作品进度列表（Top 10 按 updated_at） ────────────
    project_ids = [p.id for p in projects_rows]
    chapter_per_project = {}
    if project_ids:
        for row in (
            db.query(
                Chapter.project_id,
                sa_func.count(Chapter.id).label("cnt"),
                sa_func.coalesce(sa_func.sum(Chapter.word_count), 0).label("words"),
                sa_func.coalesce(sa_func.avg(Chapter.last_quality_score), 0).label("avg_q"),
            )
            .filter(
                Chapter.project_id.in_(project_ids),
                Chapter.deleted_at.is_(None),
            )
            .group_by(Chapter.project_id)
            .all()
        ):
            chapter_per_project[str(row.project_id)] = {
                "chapter_count": int(row.cnt),
                "actual_words": int(row.words),
                "avg_quality": round(float(row.avg_q or 0), 1),
            }

    projects_progress = []
    sorted_projects = sorted(
        projects_rows,
        key=lambda p: (p.updated_at or datetime.min),
        reverse=True,
    )[:10]
    for p in sorted_projects:
        pid = str(p.id)
        stats = chapter_per_project.get(pid, {"chapter_count": 0, "actual_words": 0, "avg_quality": 0.0})
        target = int(p.target_words or 0)
        actual = stats["actual_words"]
        pct = round(actual / target * 100, 1) if target > 0 else 0.0
        projects_progress.append({
            "id": pid,
            "title": p.title or "未命名",
            "genre": p.genre or "其他",
            "status": p.status or "drafting",
            "target_words": target,
            "actual_words": actual,
            "progress_pct": pct,
            "chapter_count": stats["chapter_count"],
            "avg_quality": stats["avg_quality"],
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        })

    # ── 8. 题材分布（Top 6 + 其他合并） ───────────────────
    sorted_genres = sorted(genre_dist.items(), key=lambda x: x[1], reverse=True)
    genre_list: List[Dict[str, Any]] = []
    others = 0
    for i, (genre, cnt) in enumerate(sorted_genres):
        if i < 6:
            genre_list.append({"genre": genre, "count": cnt})
        else:
            others += cnt
    if others > 0:
        genre_list.append({"genre": "其他", "count": others})

    return {
        # KPI
        "total_words": total_words,
        "total_projects": total_projects,
        "total_chapters": total_chapters,
        "streak_days": streak_days,
        "today_words": today_words,
        "avg_quality_score": avg_quality,
        "writing_days_30": writing_days_30,
        # 趋势
        "trend_30": trend_30,
        # 写作习惯
        "weekday_distribution": weekday_dist,
        # 作品
        "projects_progress": projects_progress,
        "status_distribution": [
            {"status": k, "count": v} for k, v in status_dist.items()
        ],
        "genre_distribution": genre_list,
        # 质检
        "total_quality_debts": total_debts,
        "debt_by_severity": debt_by_severity,
        # AI 生成
        "bootstrap_count": int(bootstrap_count),
        "ai_call_count_30": ai_call_count_30,
    }
