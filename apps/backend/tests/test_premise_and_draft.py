import pytest

from app.schemas.project import ProjectCreate, ProjectOut
from app.routers.ai import ChapterDebriefRequest
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


def test_chapter_debrief_accepts_storyline_name_without_uuid():
    req = ChapterDebriefRequest(
        chapter_id="00000000-0000-0000-0000-000000000001",
        storyline_updates=[
            {
                "storyline_name": "主线：黑雾来处",
                "append_beat": "丹虚子说明昨夜黑雾与魂殿有关。",
            }
        ],
    )

    assert req.storyline_updates[0].storyline_id is None
    assert req.storyline_updates[0].storyline_name == "主线：黑雾来处"


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


@pytest.mark.asyncio
async def test_draft_prompt_includes_continuity_ledger():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096):
        captured["prompt"] = prompt
        yield "正文"

    svc = AIService()
    svc._stream_ai = fake_stream

    async for _ in svc.draft_assist_stream(
        chapter_title="第9章：丹火再燃",
        outline_hook="萧炎察觉药鼎异动",
        outline_summary="用刚突破的六段斗之气稳定丹火",
        outline_conflict="接受实力已经改变",
        outline_highlight="丹虚子提醒魂殿气息并非凭空出现",
        outline_foreshadow="收昨夜黑雾伏笔",
        prev_chapter_tail="丹田震鸣，六段斗之气终于稳定下来。",
        world_summary="斗之气按段位递进，跌境必须有明确代价。",
        character_summary="萧炎（protagonist境界:六段斗之气）性格:倔强",
        memory_summary="第8章突破到六段斗之气",
        existing_content="",
        continuity_context=(
            "截至第8章事实表：萧炎当前境界=六段斗之气；"
            "未解决承接点：昨夜黑雾曾被丹虚子感应；"
            "禁止事项：不得写成四段斗之气，除非本章明确跌境原因。"
        ),
    ):
        pass

    assert "【连续性账本 / 不得违背】" in captured["prompt"]
    assert "当前境界=六段斗之气" in captured["prompt"]
    assert "不得写成四段斗之气" in captured["prompt"]


@pytest.mark.asyncio
async def test_auto_debrief_extracts_memory_updates_for_foreshadow_and_information_source():
    captured = {}

    async def fake_call(system: str, prompt: str, max_tokens: int = 2048):
        captured["prompt"] = prompt
        return """
        {
          "character_updates": [
            {
              "character_id": "00000000-0000-0000-0000-000000000001",
              "character_name": "萧炎",
              "current_realm": "六段斗之气"
            }
          ],
          "storyline_updates": [],
          "memory_updates": [
            {
              "memory_type": "character_state",
              "title": "萧炎突破六段斗之气",
              "content": "萧炎在第8章明确突破并稳定在六段斗之气。",
              "tags": ["萧炎", "境界"]
            },
            {
              "memory_type": "foreshadow",
              "title": "丹虚子感应黑雾",
              "content": "丹虚子通过昨夜黑雾感应到魂殿气息，第9章提及时必须回扣这个来源。",
              "tags": ["丹虚子", "魂殿", "信息来源"]
            }
          ],
          "summary": "境界和魂殿伏笔均已记录。"
        }
        """

    svc = AIService()
    svc._call_ai = fake_call

    result = await svc.auto_extract_debrief(
        chapter_content="萧炎体内斗之气稳定在六段。丹虚子沉声说，他昨夜从黑雾中感应到了魂殿气息。",
        chapter_title="第8章：丹火再燃",
        chapter_number=8,
        character_states=[
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": "萧炎",
                "current_realm": "三段斗之气",
                "current_location": "萧家",
                "current_status": "alive",
            }
        ],
        storylines=[],
    )

    assert "信息来源" in captured["prompt"]
    assert "伏笔" in captured["prompt"]
    assert result["memory_updates"] == [
        {
            "memory_type": "character_state",
            "title": "萧炎突破六段斗之气",
            "content": "萧炎在第8章明确突破并稳定在六段斗之气。",
            "tags": ["萧炎", "境界"],
        },
        {
            "memory_type": "foreshadow",
            "title": "丹虚子感应黑雾",
            "content": "丹虚子通过昨夜黑雾感应到魂殿气息，第9章提及时必须回扣这个来源。",
            "tags": ["丹虚子", "魂殿", "信息来源"],
        },
    ]


@pytest.mark.asyncio
async def test_auto_debrief_extracts_chapter_index():
    async def fake_call(system: str, prompt: str, max_tokens: int = 2048):
        assert "章节索引" in prompt
        assert "章末钩子强度" in prompt
        return """
        {
          "character_updates": [],
          "storyline_updates": [],
          "memory_updates": [],
          "chapter_index": {
            "story_day": "Day 8",
            "core_events": ["萧炎稳定六段斗之气", "丹虚子说明昨夜黑雾来源"],
            "first_appearances": [{"character_id": "", "name": "丹虚子"}],
            "actual_foreshadows_laid": [{"description": "黑雾与魂殿有关", "status": "open"}],
            "actual_foreshadows_resolved": [{"description": "昨夜异常气息来源被解释"}],
            "ending_hook": "丹虚子说魂殿已经盯上萧家",
            "hook_strength": 4,
            "continuity_notes": [{"severity": "medium", "note": "后续提到魂殿必须回扣黑雾信息来源"}]
          },
          "summary": "章节索引已生成。"
        }
        """

    svc = AIService()
    svc._call_ai = fake_call

    result = await svc.auto_extract_debrief(
        chapter_content="萧炎稳定六段斗之气。丹虚子解释昨夜黑雾与魂殿有关。",
        chapter_title="第8章：丹火再燃",
        chapter_number=8,
        character_states=[],
        storylines=[],
    )

    assert result["chapter_index"]["story_day"] == "Day 8"
    assert result["chapter_index"]["hook_strength"] == 4
    assert result["chapter_index"]["actual_foreshadows_laid"][0]["status"] == "open"


@pytest.mark.asyncio
async def test_draft_prompt_includes_chapter_index_context():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096):
        captured["prompt"] = prompt
        yield "正文"

    svc = AIService()
    svc._stream_ai = fake_stream

    async for _ in svc.draft_assist_stream(
        chapter_title="第10章：魂影入夜",
        outline_hook="黑雾再现",
        outline_summary="萧炎根据前文线索识别魂殿气息",
        outline_conflict="从被动惊疑到主动追索",
        outline_highlight="黑雾指向萧家旧案",
        outline_foreshadow="回扣昨夜黑雾",
        prev_chapter_tail="丹虚子说魂殿已经盯上萧家。",
        world_summary="斗气大陆",
        character_summary="萧炎（protagonist境界:六段斗之气）",
        memory_summary="",
        existing_content="",
        chapter_index_context="第8章：故事日Day 8；核心事件：丹虚子解释昨夜黑雾；未回收伏笔：黑雾与魂殿有关",
    ):
        pass

    assert "【章节速查索引】" in captured["prompt"]
    assert "未回收伏笔：黑雾与魂殿有关" in captured["prompt"]
