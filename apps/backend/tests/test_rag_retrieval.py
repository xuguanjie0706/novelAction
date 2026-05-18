"""RAG 检索服务单元测试（无 DB / 无 embedding）。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.rag import RagSearchHitOut
from app.services.rag_retrieval_service import (
    build_answer_hint,
    format_memory_summary,
    hits_to_schema,
    retrieve_memory_for_writing,
)


def test_format_memory_summary_compact():
    chunk = SimpleNamespace(
        chapter_number=3,
        title="反派苏醒",
        memory_type="event",
        content="反派1号在第三章末苏醒。",
    )
    s = format_memory_summary([chunk], large_context=False)
    assert "反派苏醒" in s
    assert "苏醒" in s


def test_hits_to_schema_order():
    cid = uuid4()
    chunk = SimpleNamespace(
        id=cid,
        memory_type="character_state",
        title="状态",
        content="反派1号已死亡。",
        chapter_number=10,
        tags=["反派"],
    )
    hits = hits_to_schema([(chunk, 0.91, "semantic")])
    assert len(hits) == 1
    assert hits[0].rank == 1
    assert hits[0].score == 0.91
    assert hits[0].retrieval_source == "semantic"


def test_build_answer_hint_empty():
    hint = build_answer_hint([], "反派1号起了没")
    assert "未在记忆库中找到" in hint


@pytest.mark.asyncio
async def test_recency_anchor_respects_max_chapter():
    """时序锚定应与语义检索一致，受 max_chapter 约束。"""
    db = MagicMock()
    filter_mock = MagicMock()
    order_mock = MagicMock()
    limit_mock = MagicMock()
    limit_mock.all.return_value = []
    order_mock.limit.return_value = limit_mock
    filter_mock.order_by.return_value = order_mock
    db.query.return_value.filter.return_value = filter_mock

    with patch(
        "app.services.rag_retrieval_service.semantic_search_scored",
        new_callable=AsyncMock,
        return_value=([], "ok"),
    ):
        await retrieve_memory_for_writing(
            db,
            project_id=uuid4(),
            query="反派",
            top_k_semantic=5,
            max_chapter=12,
            recency_limit=6,
        )

    # project_id 过滤后应再套 max_chapter 过滤
    assert filter_mock.filter.called


def test_build_answer_hint_with_hits():
    hit = RagSearchHitOut(
        rank=1,
        memory_id=uuid4(),
        score=0.88,
        retrieval_source="semantic",
        memory_type="event",
        title="反派结局",
        content="反派1号在终章被主角击杀。",
        content_preview="反派1号在终章被主角击杀。",
        chapter_number=99,
        tags=[],
    )
    hint = build_answer_hint([hit], "反派1号怎么死的")
    assert "反派1号怎么死的" in hint
    assert "第99章" in hint
