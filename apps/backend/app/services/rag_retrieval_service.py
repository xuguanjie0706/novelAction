"""RAG 记忆检索编排：语义召回 + 时序锚定 + 结构化落库。"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.memory import MemoryChunk
from app.models.rag_retrieval_log import RagRetrievalLog
from app.schemas.rag import RagQueryResponse, RagSearchHitOut
from app.services.embedding_service import semantic_search_scored

CONTENT_PREVIEW_LEN = 240


def _preview(text: str, limit: int = CONTENT_PREVIEW_LEN) -> str:
    t = (text or "").strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


def _truncate(text: str | None, limit: int) -> str:
    if not text:
        return ""
    t = text.strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


def format_memory_summary(
    chunks: List[MemoryChunk],
    *,
    large_context: bool = True,
) -> str:
    """将记忆片段格式化为写章 prompt 注入块。"""
    if not chunks:
        return ""
    return "\n".join(
        f"- 第{(m.chapter_number or '?')}章 "
        f"{m.title or m.memory_type}: {_truncate(m.content, 600)}"
        for m in chunks
    )


def build_answer_hint(hits: List[RagSearchHitOut], query: str) -> str:
    """基于 Top 命中生成可读摘要（不额外调用 LLM）。"""
    if not hits:
        return f"未在记忆库中找到与「{query}」相关的条目，请检查是否已复盘提取记忆或尝试换关键词。"
    lines = [f"针对「{query}」，记忆库中最相关的 {min(len(hits), 5)} 条："]
    for h in hits[:5]:
        ch = f"第{h.chapter_number}章" if h.chapter_number else "设定"
        score_txt = f"相关度 {h.score:.2f}" if h.score is not None else "时序补充"
        lines.append(
            f"{h.rank}. [{ch}·{h.memory_type}] {h.title or '（无标题）'}（{score_txt}）\n"
            f"   {h.content_preview}"
        )
    return "\n".join(lines)


def hits_to_schema(
    ranked: List[Tuple[MemoryChunk, Optional[float], str]],
) -> List[RagSearchHitOut]:
    out: List[RagSearchHitOut] = []
    for i, (chunk, score, source) in enumerate(ranked, start=1):
        src: str = source if source in ("semantic", "recency_anchor", "recency_fallback") else "semantic"
        out.append(
            RagSearchHitOut(
                rank=i,
                memory_id=chunk.id,
                score=round(score, 4) if score is not None else None,
                retrieval_source=src,  # type: ignore[arg-type]
                memory_type=chunk.memory_type or "event",
                title=chunk.title,
                content=chunk.content or "",
                content_preview=_preview(chunk.content or ""),
                chapter_number=chunk.chapter_number,
                tags=list(chunk.tags or []),
            )
        )
    return out


async def retrieve_memory_for_writing(
    db: Session,
    *,
    project_id: str | UUID,
    query: str,
    top_k_semantic: int,
    max_chapter: Optional[int],
    recency_limit: int = 6,
    memory_types: Optional[List[str]] = None,
) -> Tuple[List[MemoryChunk], str, List[Tuple[MemoryChunk, Optional[float], str]]]:
    """
    写章路径：语义 Top-K + 最近 N 条去重合并。

    Returns:
        merged_chunks, overall_status, ranked_detail（含分数与来源）
    """
    q = (query or "").strip()
    if not q:
        return [], "empty_query", []

    scored, status = await semantic_search_scored(
        db,
        project_id,
        q,
        top_k=top_k_semantic,
        memory_types=memory_types,
        max_chapter=max_chapter,
    )

    recent_q = db.query(MemoryChunk).filter(MemoryChunk.project_id == str(project_id))
    if max_chapter is not None:
        recent_q = recent_q.filter(
            or_(
                MemoryChunk.chapter_number.is_(None),
                MemoryChunk.chapter_number <= int(max_chapter),
            )
        )
    recent = (
        recent_q.order_by(func.coalesce(MemoryChunk.chapter_number, 0).desc())
        .limit(recency_limit)
        .all()
    )

    seen = {c.id for c, _, _ in scored}
    ranked: List[Tuple[MemoryChunk, Optional[float], str]] = list(scored)
    for c in recent:
        if c.id in seen:
            continue
        ranked.append((c, None, "recency_anchor"))
        seen.add(c.id)

    merged = [c for c, _, _ in ranked]
    return merged, status, ranked


async def retrieve_and_log_pre_write_memory(
    db: Session,
    *,
    project_id: str | UUID,
    chapter_id: Optional[str | UUID],
    query: str,
    top_k: int = 40,
    max_chapter: Optional[int] = None,
    commit: bool = True,
) -> Tuple[List[MemoryChunk], RagRetrievalLog]:
    """
    写前预警路径：语义 Top-K 检索并落库（source=pre_write_warning）。

    与旧逻辑一致：不做时序锚定（recency_limit=0），仅语义 Top-K。
    """
    started = time.perf_counter()
    merged, status, ranked = await retrieve_memory_for_writing(
        db,
        project_id=project_id,
        query=query,
        top_k_semantic=top_k,
        max_chapter=max_chapter,
        recency_limit=0,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    hits = hits_to_schema(ranked[:top_k])
    summary = format_memory_summary(merged[:top_k], large_context=True)

    row = persist_rag_log(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        source="pre_write_warning",
        status=status,
        duration_ms=duration_ms,
        input_payload={
            "query": (query or "").strip(),
            "top_k": top_k,
            "max_chapter": max_chapter,
            "recency_limit": 0,
        },
        output_payload={
            "hits": [h.model_dump(mode="json") for h in hits],
            "memory_summary": summary,
            "answer_hint": build_answer_hint(hits, (query or "").strip()),
            "hit_count": len(hits),
        },
        commit=commit,
    )
    return merged, row


async def retrieve_and_log_draft_context(
    db: Session,
    *,
    project_id: str | UUID,
    chapter_id: Optional[str | UUID],
    query: str,
    top_k_semantic: int,
    max_chapter: Optional[int],
    recency_limit: int = 6,
    large_context: bool = True,
    commit: bool = False,
) -> Tuple[List[MemoryChunk], str, RagRetrievalLog, Dict[str, Any]]:
    """
    写章构建上下文：语义 + 时序锚定，落库 source=draft_context。

    Returns:
        merged_chunks, memory_summary, log_row, client_snapshot（SSE 用）
    """
    started = time.perf_counter()
    q = (query or "").strip()
    if not q:
        row = persist_rag_log(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            source="draft_context",
            status="empty_query",
            duration_ms=0,
            input_payload={"query": "", "top_k_semantic": top_k_semantic, "max_chapter": max_chapter},
            output_payload={"hits": [], "memory_summary": "", "hit_count": 0},
            commit=commit,
        )
        snap = client_snapshot_from_log(row)
        return [], "", row, snap

    merged, status, ranked = await retrieve_memory_for_writing(
        db,
        project_id=project_id,
        query=q,
        top_k_semantic=top_k_semantic,
        max_chapter=max_chapter,
        recency_limit=recency_limit,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    hits = hits_to_schema(ranked)
    memory_summary = format_memory_summary(merged, large_context=large_context)

    row = persist_rag_log(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        source="draft_context",
        status=status,
        duration_ms=duration_ms,
        input_payload={
            "query": q,
            "top_k_semantic": top_k_semantic,
            "max_chapter": max_chapter,
            "recency_limit": recency_limit,
            "large_context": large_context,
        },
        output_payload={
            "hits": [h.model_dump(mode="json") for h in hits],
            "memory_summary": memory_summary,
            "hit_count": len(hits),
        },
        commit=commit,
    )
    return merged, memory_summary, row, client_snapshot_from_log(row)


async def retrieve_and_log_suggest_memory(
    db: Session,
    *,
    project_id: str | UUID,
    chapter_id: Optional[str | UUID],
    query: str,
    top_k: int = 5,
    max_chapter: Optional[int] = None,
    rag_context: str = "",
    extra_output: Optional[Dict[str, Any]] = None,
    commit: bool = True,
) -> Tuple[List[MemoryChunk], RagRetrievalLog]:
    """写作建议流：语义记忆检索落库（source=suggest）。"""
    started = time.perf_counter()
    q = (query or "").strip()
    if not q:
        row = persist_rag_log(
            db,
            project_id=project_id,
            chapter_id=chapter_id,
            source="suggest",
            status="empty_query",
            duration_ms=0,
            input_payload={"query": "", "top_k": top_k, "max_chapter": max_chapter},
            output_payload={
                "hits": [],
                "hit_count": 0,
                "rag_context_preview": "",
                **(extra_output or {}),
            },
            commit=commit,
        )
        return [], row

    merged, status, ranked = await retrieve_memory_for_writing(
        db,
        project_id=project_id,
        query=q,
        top_k_semantic=top_k,
        max_chapter=max_chapter,
        recency_limit=0,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    hits = hits_to_schema(ranked[:top_k])

    row = persist_rag_log(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        source="suggest",
        status=status,
        duration_ms=duration_ms,
        input_payload={
            "query": q,
            "top_k": top_k,
            "max_chapter": max_chapter,
            "recency_limit": 0,
        },
        output_payload={
            "hits": [h.model_dump(mode="json") for h in hits],
            "memory_summary": format_memory_summary(merged[:top_k]),
            "hit_count": len(hits),
            "rag_context_preview": _preview(rag_context, 1200),
            **(extra_output or {}),
        },
        commit=commit,
    )
    return merged, row


def patch_rag_log_output(
    db: Session,
    row: RagRetrievalLog,
    updates: Dict[str, Any],
    *,
    commit: bool = True,
) -> None:
    """合并更新已落库日志的 output_payload（如 suggest 流事后写入 rag_context_preview）。"""
    merged = dict(row.output_payload or {})
    merged.update(updates)
    row.output_payload = merged
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()


def persist_rag_log(
    db: Session,
    *,
    project_id: str | UUID,
    chapter_id: Optional[str | UUID],
    source: str,
    status: str,
    duration_ms: int,
    input_payload: Dict[str, Any],
    output_payload: Dict[str, Any],
    commit: bool = True,
) -> RagRetrievalLog:
    row = RagRetrievalLog(
        project_id=str(project_id),
        chapter_id=str(chapter_id) if chapter_id else None,
        source=source,
        status=status,
        duration_ms=duration_ms,
        input_payload=input_payload,
        output_payload=output_payload,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


async def run_rag_query(
    db: Session,
    *,
    project_id: str | UUID,
    query: str,
    top_k: int = 20,
    max_chapter: Optional[int] = None,
    memory_types: Optional[List[str]] = None,
    chapter_id: Optional[str | UUID] = None,
    include_injected_summary: bool = True,
    source: str = "rag_query",
) -> RagQueryResponse:
    """手动 / 调试向结构化 RAG 查询。"""
    started = time.perf_counter()
    merged, status, ranked = await retrieve_memory_for_writing(
        db,
        project_id=project_id,
        query=query,
        top_k_semantic=top_k,
        max_chapter=max_chapter,
        recency_limit=0 if source == "rag_query" else 6,
        memory_types=memory_types,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    hits = hits_to_schema(ranked[:top_k])
    summary = format_memory_summary(merged[:top_k], large_context=True) if include_injected_summary else ""
    answer_hint = build_answer_hint(hits, query.strip())

    params: Dict[str, Any] = {
        "top_k": top_k,
        "max_chapter": max_chapter,
        "memory_types": memory_types,
        "chapter_id": str(chapter_id) if chapter_id else None,
    }
    output_payload: Dict[str, Any] = {
        "hits": [h.model_dump(mode="json") for h in hits],
        "memory_summary": summary,
        "answer_hint": answer_hint,
        "hit_count": len(hits),
    }
    input_payload = {"query": query.strip(), **params}

    row = persist_rag_log(
        db,
        project_id=project_id,
        chapter_id=chapter_id,
        source=source,
        status=status,
        duration_ms=duration_ms,
        input_payload=input_payload,
        output_payload=output_payload,
    )

    return RagQueryResponse(
        log_id=row.id,
        query=query.strip(),
        params=params,
        status=status,
        duration_ms=duration_ms,
        hits=hits,
        memory_summary=summary,
        answer_hint=answer_hint,
    )


def client_snapshot_from_log(row: RagRetrievalLog) -> Dict[str, Any]:
    """SSE / 前端展示用的精简快照。"""
    out = row.output_payload or {}
    inp = row.input_payload or {}
    hits = out.get("hits") or []
    return {
        "event": "rag_context",
        "log_id": str(row.id),
        "source": row.source,
        "status": row.status,
        "query": inp.get("query") or "",
        "hit_count": out.get("hit_count") or len(hits),
        "hits": hits[:12],
        "memory_summary_preview": _preview(out.get("memory_summary") or "", 800),
        "answer_hint": out.get("answer_hint") or "",
    }
