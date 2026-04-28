import pytest

from app.schemas.project import ProjectCreate, ProjectOut
from app.services.ai_service import AIService


def test_project_schema_carries_premise():
    premise = "# 立意与类型\n每章都要服务于废柴逆袭的爽感与命题。"

    created = ProjectCreate(title="苍穹丹祖", premise=premise)

    assert created.premise == premise

    out = ProjectOut(
        id="00000000-0000-0000-0000-000000000001",
        title="苍穹丹祖",
        genre="玄幻",
        logline="废柴少年重建丹田",
        premise=premise,
        world_overview=None,
        story_core={},
        status="drafting",
        target_words=None,
        cover_url=None,
        created_at="2026-04-28T00:00:00Z",
        updated_at=None,
    )

    assert out.premise == premise


@pytest.mark.asyncio
async def test_draft_prompt_includes_premise_and_full_chapter_target():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096):
        captured["system"] = system
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        yield "正文"

    svc = AIService()
    svc._stream_ai = fake_stream

    chunks = []
    async for chunk in svc.draft_assist_stream(
        chapter_title="第1章：臭水沟里的传承",
        outline_hook="污水将落，玄尘传承觉醒",
        outline_summary="苏辰被辱后获得传承",
        outline_conflict="从自我怀疑到重新抬头",
        outline_highlight="苍穹三千年，我等的人，就是你",
        outline_foreshadow="丹田被毁另有真凶",
        prev_chapter_tail="",
        world_summary="云天宗以丹道论尊卑",
        character_summary="苏辰（protagonist）性格:沉默不服输",
        memory_summary="",
        existing_content="",
        premise="# 立意与类型\n目标读者：番茄男频。主题：重写命运。",
    ):
        chunks.append(chunk)

    assert chunks == ["正文"]
    assert "【立意与类型 / PREMISE】" in captured["prompt"]
    assert "目标读者：番茄男频" in captured["prompt"]
    assert "2200-2400字" in captured["prompt"]
    assert "约600字" not in captured["prompt"]
    assert captured["max_tokens"] >= 4096
