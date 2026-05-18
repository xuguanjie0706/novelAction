"""RAG 落库辅助函数测试。"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.rag_retrieval_service import retrieve_and_log_pre_write_memory


@pytest.mark.asyncio
async def test_retrieve_and_log_pre_write_memory_persists_source():
    chunk = MagicMock()
    chunk.id = uuid4()
    chunk.memory_type = "event"
    chunk.title = "反派结局"
    chunk.content = "反派1号死亡"
    chunk.chapter_number = 10
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
    ) as persist:
        merged, row = await retrieve_and_log_pre_write_memory(
            MagicMock(),
            project_id=uuid4(),
            chapter_id=uuid4(),
            query="反派1号怎么死的",
            top_k=40,
            max_chapter=20,
            commit=False,
        )
        assert len(merged) == 1
        assert row is mock_row
        persist.assert_called_once()
        call_kw = persist.call_args.kwargs
        assert call_kw["source"] == "pre_write_warning"
        assert call_kw["input_payload"]["recency_limit"] == 0
