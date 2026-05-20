from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Chapter, MemoryChunk
from app.models.rag_retrieval_log import RagRetrievalLog
from app.schemas import MemoryChunkOut
from app.schemas.memory import MemoryConflictReport
from app.schemas.rag import RagQueryRequest, RagQueryResponse, RagRetrievalLogOut
from app.services.ai_service import AIService
from app.services.embedding_service import embed_chunk_async, semantic_search
from app.services.memory_conflict_detector import detect_memory_conflicts
from app.services.rag_retrieval_service import run_rag_query
from app.utils.chapter_numbering import display_chapter_number
from app.utils.memory_extract import sanitize_extracted_memory_item

router = APIRouter()


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
        fields = sanitize_extracted_memory_item(item)
        if fields is None:
            continue
        chunk = MemoryChunk(
            project_id=project_id,
            chapter_id=chapter_id,
            chapter_number=chapter_no,
            **fields,
        )
        db.add(chunk)
        results.append(chunk)
    db.commit()
    for r in results:
        db.refresh(r)

    for r in results:
        embed_text = f"{r.title or ''}\n{r.content}".strip()
        embed_chunk_async(r.id, embed_text, SessionLocal)

    return results


@router.post("/memory/rag-query", response_model=RagQueryResponse)
async def rag_query_memory(
    project_id: str,
    req: RagQueryRequest,
    db: Session = Depends(get_db),
):
    """
    结构化 RAG 查询：自然语言问题 → 语义命中列表 + 注入摘要 + 可读 answer_hint。

    示例：「反派1号起了没」「反派1号怎么死的」
    """
    if req.chapter_id:
        ch = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if not ch:
            raise HTTPException(404, "Chapter not found")
    memory_types = [t.strip() for t in req.types.split(",")] if req.types else None
    return await run_rag_query(
        db,
        project_id=project_id,
        query=req.q,
        top_k=req.top_k,
        max_chapter=req.max_chapter,
        memory_types=memory_types,
        chapter_id=req.chapter_id,
        include_injected_summary=req.include_injected_summary,
        source="rag_query",
    )


@router.get("/memory/rag-logs", response_model=List[RagRetrievalLogOut])
def list_rag_logs(
    project_id: str,
    chapter_id: Optional[UUID] = None,
    source: Optional[str] = Query(
        None,
        description="draft_context | pre_write_warning | suggest | rag_query",
    ),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """查询项目 RAG 检索日志（写章 / 手动查询）。"""
    q = db.query(RagRetrievalLog).filter(RagRetrievalLog.project_id == project_id)
    if chapter_id is not None:
        q = q.filter(RagRetrievalLog.chapter_id == str(chapter_id))
    if source:
        q = q.filter(RagRetrievalLog.source == source)
    return q.order_by(RagRetrievalLog.created_at.desc()).limit(limit).all()


@router.get("/memory/rag-logs/{log_id}", response_model=RagRetrievalLogOut)
def get_rag_log(
    project_id: str,
    log_id: UUID,
    db: Session = Depends(get_db),
):
    row = (
        db.query(RagRetrievalLog)
        .filter(RagRetrievalLog.project_id == project_id, RagRetrievalLog.id == log_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "RAG log not found")
    return row


@router.get("/memory/search", response_model=List[MemoryChunkOut])
async def search_memory(
    project_id: str,
    q: str,
    top_k: int = 20,
    types: Optional[str] = None,
    max_chapter: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    语义记忆检索端点。

    使用 pgvector 余弦距离检索与 q 最相关的记忆条目；
    pgvector 不可用时自动降级为时序排列。

    Args:
        q: 查询文本，例如「青玄剑」「主角突破金丹期」「叛徒身份」
        top_k: 返回条数（默认 20，上限 100）
        types: 逗号分隔的 memory_type 过滤，如 ``foreshadow,event``；
               不传则不过滤类型
        max_chapter: 只检索该章节编号及之前的记忆，防止泄漏未发生的剧情
    """
    if not q or not q.strip():
        raise HTTPException(400, "q 不能为空")
    top_k = max(1, min(top_k, 100))
    memory_types = [t.strip() for t in types.split(",")] if types else None

    results = await semantic_search(
        db,
        project_id,
        q.strip(),
        top_k=top_k,
        memory_types=memory_types,
        max_chapter=max_chapter,
    )
    return results


@router.post("/memory/reembed")
async def reembed_memory(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    对 embedding 为 NULL 的 MemoryChunk 批量重新触发向量化（fire-and-forget）。

    用途：首次部署 pgvector 或 Embedding 服务重启后，对存量数据补跑 embedding，
    使语义检索（RAG）能召回所有历史记忆片段。

    Returns:
        queued: 已入队向量化的条目数
        skipped: embedding 已存在、无需补跑的条目数
    """
    # 用原生 SQL 过滤 NULL embedding，规避 pgvector 条件导入时 Column 可能未挂载的问题
    rows = db.execute(
        text(
            "SELECT id, title, content FROM memory_chunks "
            "WHERE project_id = :pid AND embedding IS NULL"
        ),
        {"pid": str(project_id)},
    ).fetchall()

    total = db.execute(
        text("SELECT COUNT(*) FROM memory_chunks WHERE project_id = :pid"),
        {"pid": str(project_id)},
    ).scalar()

    for row in rows:
        embed_text = f"{row.title or ''}\n{row.content or ''}".strip()
        if embed_text:
            embed_chunk_async(UUID(str(row.id)), embed_text, SessionLocal)

    queued = len(rows)
    skipped = (total or 0) - queued
    return {"queued": queued, "skipped": skipped, "total": total or 0}


@router.get("/memory", response_model=List[MemoryChunkOut])
def list_memory(
    project_id: str,
    memory_type: Optional[str] = None,
    sort_by: Optional[str] = Query(
        None,
        description="排序字段：chapter（默认）/ importance / access_count / recent_access",
    ),
    db: Session = Depends(get_db),
):
    """
    列出项目记忆库。

    Args:
        sort_by: 排序方式
          - chapter（默认）：按章节顺序升序
          - importance：按 importance_score 降序（重要度优先）
          - access_count：按被召回次数降序（热门记忆优先）
          - recent_access：按最近访问时间降序
    """
    q = (
        db.query(MemoryChunk)
        .outerjoin(Chapter, Chapter.id == MemoryChunk.chapter_id)
        .filter(MemoryChunk.project_id == project_id)
    )
    if memory_type:
        q = q.filter(MemoryChunk.memory_type == memory_type)

    if sort_by == "importance":
        q = q.order_by(MemoryChunk.importance_score.desc().nullslast())
    elif sort_by == "access_count":
        q = q.order_by(MemoryChunk.access_count.desc().nullslast())
    elif sort_by == "recent_access":
        q = q.order_by(MemoryChunk.last_accessed_at.desc().nullslast())
    else:
        q = q.order_by(
            func.coalesce(Chapter.sort_order, MemoryChunk.chapter_number, 0).asc(),
            MemoryChunk.created_at,
        )
    return q.all()


@router.post("/memory/detect-conflicts", response_model=MemoryConflictReport)
async def detect_conflicts(
    project_id: str,
    model_profile: Literal["local", "gemini"] = "local",
    llm_provider_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """
    AI 驱动的记忆冲突自动检测。

    扫描项目全量 MemoryChunk（最多 200 条），通过 LLM 识别以下四类冲突：
    - character_state：角色状态前后矛盾
    - timeline：时间线逻辑矛盾
    - attribute：实体属性描述冲突
    - foreshadow：伏笔管理冲突

    检测结果持久化写入 Project.extra.memory_conflicts，同时在响应中返回。

    Returns:
        total_chunks_scanned: 扫描的记忆条目总数
        conflicts: 冲突列表（含 conflict_type / severity / description / chunk_ids / chapter_refs）
        detected_at: 检测时间（ISO 格式）
    """
    svc = AIService(
        "gemini" if model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=llm_provider_id,
    )
    report = await detect_memory_conflicts(
        db,
        project_id=project_id,
        ai_service=svc,
    )
    return report


@router.get("/memory/rag-metrics")
def get_rag_metrics(
    project_id: str,
    days: int = Query(7, ge=1, le=90, description="统计最近 N 天的数据"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    RAG 命中率质量监控指标。

    从 rag_retrieval_logs 表实时聚合，无需额外存储。

    Returns:
        total_queries:       时间窗口内总查询次数
        semantic_hit_rate:   语义命中（status=ok）占比
        fallback_rate:       时序兜底（fallback_recency / embed_failed）占比
        zero_hit_rate:       零命中（hit_count=0）占比
        avg_hit_count:       平均每次查询命中条目数
        avg_duration_ms:     平均检索耗时（ms）
        by_source:           按 source 细分的各项指标
        daily_trend:         近 N 天每日查询量与语义命中率趋势
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        db.query(RagRetrievalLog)
        .filter(
            RagRetrievalLog.project_id == project_id,
            RagRetrievalLog.created_at >= since,
        )
        .order_by(RagRetrievalLog.created_at.asc())
        .all()
    )

    if not rows:
        return {
            "total_queries": 0,
            "semantic_hit_rate": None,
            "fallback_rate": None,
            "zero_hit_rate": None,
            "avg_hit_count": None,
            "avg_duration_ms": None,
            "by_source": {},
            "daily_trend": [],
        }

    def _hit_count(row: RagRetrievalLog) -> int:
        return int((row.output_payload or {}).get("hit_count") or 0)

    total = len(rows)
    semantic_ok = sum(1 for r in rows if r.status == "ok")
    fallback_n = sum(1 for r in rows if r.status in ("fallback_recency", "embed_failed"))
    zero_hit = sum(1 for r in rows if _hit_count(r) == 0)
    hit_counts = [_hit_count(r) for r in rows]
    durations = [r.duration_ms for r in rows]

    # 按 source 细分
    sources: Dict[str, Dict] = {}
    for r in rows:
        src = r.source or "unknown"
        if src not in sources:
            sources[src] = {"total": 0, "semantic_ok": 0, "zero_hit": 0, "duration_sum": 0}
        sources[src]["total"] += 1
        if r.status == "ok":
            sources[src]["semantic_ok"] += 1
        if _hit_count(r) == 0:
            sources[src]["zero_hit"] += 1
        sources[src]["duration_sum"] += r.duration_ms or 0

    by_source: Dict[str, Any] = {}
    for src, stats in sources.items():
        n = stats["total"]
        by_source[src] = {
            "total": n,
            "semantic_hit_rate": round(stats["semantic_ok"] / n, 3) if n else None,
            "zero_hit_rate": round(stats["zero_hit"] / n, 3) if n else None,
            "avg_duration_ms": round(stats["duration_sum"] / n) if n else None,
        }

    # 每日趋势（UTC 日期分组）
    daily: Dict[str, Dict] = {}
    for r in rows:
        day = r.created_at.strftime("%Y-%m-%d") if r.created_at else "unknown"
        if day not in daily:
            daily[day] = {"queries": 0, "semantic_ok": 0}
        daily[day]["queries"] += 1
        if r.status == "ok":
            daily[day]["semantic_ok"] += 1

    daily_trend = [
        {
            "date": day,
            "queries": v["queries"],
            "semantic_hit_rate": round(v["semantic_ok"] / v["queries"], 3) if v["queries"] else None,
        }
        for day, v in sorted(daily.items())
    ]

    return {
        "total_queries": total,
        "semantic_hit_rate": round(semantic_ok / total, 3),
        "fallback_rate": round(fallback_n / total, 3),
        "zero_hit_rate": round(zero_hit / total, 3),
        "avg_hit_count": round(sum(hit_counts) / total, 2),
        "avg_duration_ms": round(sum(durations) / total),
        "by_source": by_source,
        "daily_trend": daily_trend,
    }
