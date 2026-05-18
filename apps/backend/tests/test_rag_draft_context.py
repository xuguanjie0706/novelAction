"""写章 draft_context RAG 落库测试。"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.rag_retrieval_service import retrieve_and_log_draft_context


@pytest.mark.asyncio
async def test_retrieve_and_log_draft_context_records_duration():
    chunk = MagicMock()
    chunk.id = uuid4()
    chunk.memory_type = "event"
    chunk.title = "t"
    chunk.content = "c"
    chunk.chapter_number = 1
    chunk.tags = []

    mock_row = MagicMock()
    mock_row.id = uuid4()

    with patch(
        "app.services.rag_retrieval_service.retrieve_memory_for_writing",
        new_callable=AsyncMock,
        return_value=([chunk], "ok", [(chunk, 0.9, "semantic")]),
    ), patch(
        "app.services.rag_retrieval_service.persist_rag_log",
        return_value=mock_row,
    ) as persist, patch(
        "app.services.rag_retrieval_service.client_snapshot_from_log",
        return_value={"event": "rag_context"},
    ):
        merged, summary, row, snap = await retrieve_and_log_draft_context(
            MagicMock(),
            project_id=uuid4(),
            chapter_id=uuid4(),
            query="test query",
            top_k_semantic=10,
            max_chapter=5,
            commit=False,
        )
        assert len(merged) == 1
        assert summary
        assert snap["event"] == "rag_context"
        assert persist.call_args.kwargs["source"] == "draft_context"
        assert persist.call_args.kwargs["duration_ms"] >= 0
