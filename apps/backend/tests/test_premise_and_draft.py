import pytest

from app.schemas.project import ProjectCreate, ProjectOut
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.faction import Faction
from app.models.foreshadow import Foreshadow
from app.models.item import Item
from app.models.outline import OutlineNode
from app.models.skill import Skill
from app.routers.foreshadows import _repair_duplicate_codes
from app.routers.ai import (
    AssetUpdates,
    ChapterDebriefRequest,
    ChapterIndexPayload,
    NewItemAsset,
    _apply_asset_updates,
    _build_writing_brief_context,
    _foreshadow_payload_from_index_item,
    _sync_chapter_index_foreshadows,
)
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


def test_foreshadow_payload_parses_ai_index_marker():
    payload = _foreshadow_payload_from_index_item(
        {
            "description": "F-017：林家火灵晶矿脉的异常震动，暗示地下矿脉被非法开采或藏有异宝（ch_015回收）",
            "status": "open",
        }
    )

    assert payload == {
        "code": "F-017",
        "title": "林家火灵晶矿脉的异常震动，暗示地下矿脉被非法开采或藏有异宝",
        "description": "林家火灵晶矿脉的异常震动，暗示地下矿脉被非法开采或藏有异宝（ch_015回收）",
        "planned_resolve_chapter": 15,
        "planned_action": "resolve",
        "status": "open",
    }


def test_foreshadow_payload_parses_develop_marker():
    payload = _foreshadow_payload_from_index_item(
        {
            "description": "F-037：慕容倾城展现的冰系法则强度远超同阶，暗示其在圣地获得了极高的造化，但可能也付出了某种代价（ch_029铺垫）。",
            "status": "open",
        }
    )

    assert payload == {
        "code": "F-037",
        "title": "慕容倾城展现的冰系法则强度远超同阶，暗示其在圣地获得了极高的造化，但可能也付出了某种代价",
        "description": "慕容倾城展现的冰系法则强度远超同阶，暗示其在圣地获得了极高的造化，但可能也付出了某种代价（ch_029铺垫）。",
        "planned_resolve_chapter": 29,
        "planned_action": "develop",
        "status": "open",
    }


def test_sync_chapter_index_foreshadows_creates_global_record():
    class EmptyQuery:
        def filter(self, *args):
            return self

        def count(self):
            return 0

        def first(self):
            return None

    class FakeDb:
        def __init__(self):
            self.added = []

        def query(self, model):
            return EmptyQuery()

        def add(self, obj):
            self.added.append(obj)

    db = FakeDb()
    chapter = Chapter(
        id="00000000-0000-0000-0000-000000000015",
        project_id="00000000-0000-0000-0000-000000000001",
        title="第15章：火灵晶矿",
        sort_order=14,
    )
    chapter_index = ChapterIndexPayload(
        actual_foreshadows_laid=[
            {
                "description": "F-017：林家火灵晶矿脉的异常震动，暗示地下矿脉被非法开采或藏有异宝（ch_015回收）",
                "status": "open",
            }
        ]
    )

    stats = _sync_chapter_index_foreshadows(
        db,
        "00000000-0000-0000-0000-000000000001",
        chapter,
        chapter_index,
    )

    assert stats == {"created": 1, "updated": 0, "resolved": 0}
    assert len(db.added) == 1
    foreshadow = db.added[0]
    assert foreshadow.code == "F-017"
    assert foreshadow.title == "林家火灵晶矿脉的异常震动，暗示地下矿脉被非法开采或藏有异宝"
    assert foreshadow.laid_chapter_number == 15
    assert foreshadow.planned_resolve_chapter == 15
    assert foreshadow.planned_action == "resolve"
    assert foreshadow.status == "open"


def test_sync_chapter_index_foreshadows_assigns_unique_codes_for_batch_items_without_codes():
    class EmptyQuery:
        def __init__(self):
            self.calls = 0

        def filter(self, *args):
            return self

        def count(self):
            return 0

        def first(self):
            return None

        def all(self):
            return []

    class FakeDb:
        def __init__(self):
            self.added = []
            self.query_obj = EmptyQuery()

        def query(self, model):
            return self.query_obj

        def add(self, obj):
            self.added.append(obj)

    db = FakeDb()
    chapter = Chapter(
        id="00000000-0000-0000-0000-000000000016",
        project_id="00000000-0000-0000-0000-000000000001",
        title="第16章：邪火初现",
        sort_order=15,
    )
    chapter_index = ChapterIndexPayload(
        actual_foreshadows_laid=[
            {"description": "赵无极提到的圣地软甲防守能力，为林炎杀招能否奏效埋下悬念"},
            {"description": "焚老沉睡前的警告，暗示神碑封印动摇（ch_022回收）"},
        ]
    )

    stats = _sync_chapter_index_foreshadows(
        db,
        "00000000-0000-0000-0000-000000000001",
        chapter,
        chapter_index,
    )

    assert stats == {"created": 2, "updated": 0, "resolved": 0}
    assert [f.code for f in db.added] == ["F-001", "F-002"]


def test_repair_duplicate_foreshadow_codes_keeps_first_and_renumbers_duplicates():
    items = [
        Foreshadow(code="F-001", title="第一条"),
        Foreshadow(code="F-001", title="重复一"),
        Foreshadow(code="F-004", title="第四条"),
        Foreshadow(code="F-004", title="重复四"),
    ]

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return items

    class FakeDb:
        def __init__(self):
            self.committed = False

        def query(self, model):
            return FakeQuery()

        def commit(self):
            self.committed = True

    db = FakeDb()

    _repair_duplicate_codes(db, "00000000-0000-0000-0000-000000000001")

    assert [item.code for item in items] == ["F-001", "F-002", "F-004", "F-005"]
    assert db.committed is True


def test_writing_brief_context_activates_bound_assets_and_factions():
    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def limit(self, *_args):
            return self

        def all(self):
            return self.rows

    class FakeDb:
        def __init__(self):
            self.rows_by_model = {}

        def query(self, model):
            return FakeQuery(self.rows_by_model.get(model, []))

    faction = Faction(
        id="00000000-0000-0000-0000-000000000011",
        project_id="00000000-0000-0000-0000-000000000001",
        name="丹火盟",
        alignment="protagonist",
        attitude_to_protagonist="neutral",
        goals="寻找焚荒传承",
        resources="丹塔内层资格",
    )
    character = Character(
        id="00000000-0000-0000-0000-000000000101",
        project_id="00000000-0000-0000-0000-000000000001",
        name="林炎",
        faction_id=faction.id,
        owned_items=[
            {
                "item_id": "00000000-0000-0000-0000-000000000201",
                "item_name": "焚荒古戒",
            }
        ],
        known_skills=[
            {
                "skill_id": "00000000-0000-0000-0000-000000000301",
                "skill_name": "焚天诀",
                "mastery": "初窥门径",
            }
        ],
    )
    item = Item(
        id="00000000-0000-0000-0000-000000000201",
        project_id="00000000-0000-0000-0000-000000000001",
        name="焚荒古戒",
        item_type="artifact",
        rarity="unique",
        effects="辅助炼化世间万火",
        limitations="过度抽取戒能会沉睡",
        status="stirred",
        story_significance="主角与焚老建立联系的纽带",
    )
    skill = Skill(
        id="00000000-0000-0000-0000-000000000301",
        project_id="00000000-0000-0000-0000-000000000001",
        name="焚天诀",
        skill_type="combat",
        grade="divine",
        effects="催动一缕荒火",
        limitations="境界不足时反噬经脉",
    )
    outline = OutlineNode(
        id="00000000-0000-0000-0000-000000000401",
        project_id="00000000-0000-0000-0000-000000000001",
        title="第7章",
        involved_character_ids=[str(character.id)],
        key_item_ids=[str(item.id)],
        key_skill_ids=[str(skill.id)],
    )
    chapter = Chapter(title="第7章：火戒初醒", sort_order=6)
    db = FakeDb()
    db.rows_by_model = {
        Character: [character],
        Faction: [faction],
        Item: [item],
        Skill: [skill],
    }

    brief = _build_writing_brief_context(
        db=db,
        project_id="00000000-0000-0000-0000-000000000001",
        chapter=chapter,
        outline_node=outline,
        large_context=False,
    )

    assert "【本章写前 Brief / 激活资产】" in brief
    assert "激活势力：丹火盟" in brief
    assert "激活道具/法宝：焚荒古戒" in brief
    assert "辅助炼化世间万火" in brief
    assert "激活功法/技能：焚天诀" in brief
    assert "境界不足时反噬经脉" in brief
    assert "C级临时资产" in brief


def test_apply_asset_updates_creates_b_tier_item_and_links_owner():
    class QueryByModel:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *args):
            return self

        def first(self):
            return self.rows[0] if self.rows else None

    class FakeDb:
        def __init__(self, character):
            self.character = character
            self.items = []
            self.added = []

        def query(self, model):
            if model is Character:
                return QueryByModel([self.character])
            if model is Item:
                return QueryByModel(self.items)
            return QueryByModel([])

        def add(self, obj):
            self.added.append(obj)
            if isinstance(obj, Item):
                self.items.append(obj)

    character = Character(
        id="00000000-0000-0000-0000-000000000101",
        project_id="00000000-0000-0000-0000-000000000001",
        name="林炎",
        owned_items=[],
    )
    db = FakeDb(character)
    chapter = Chapter(
        id="00000000-0000-0000-0000-000000000007",
        project_id="00000000-0000-0000-0000-000000000001",
        title="第7章：火戒初醒",
        sort_order=6,
    )

    stats = _apply_asset_updates(
        db=db,
        project_id="00000000-0000-0000-0000-000000000001",
        chapter=chapter,
        asset_updates=AssetUpdates(
            new_items=[
                NewItemAsset(
                    tier="B",
                    name="涅槃火精残息",
                    item_type="material",
                    rarity="rare",
                    description="古戒感应到的一缕火精残息。",
                    effects="可辅助后续突破。",
                    limitations="本章不能直接炼化完整火精。",
                    current_owner_id=str(character.id),
                    story_significance="作为焚荒古戒苏醒后的第一条资源线索。",
                )
            ]
        ),
    )

    assert stats == {"created_items": 1, "updated_items": 0, "created_skills": 0, "updated_skills": 0, "created_factions": 0, "updated_factions": 0}
    assert len(db.added) == 1
    created_item = db.added[0]
    assert created_item.name == "涅槃火精残息"
    assert created_item.first_appearance_chapter == 7
    assert created_item.extra["asset_tier"] == "B"
    assert character.owned_items == [
        {
            "item_id": str(created_item.id),
            "item_name": "涅槃火精残息",
            "acquired_chapter": 7,
        }
    ]


@pytest.mark.asyncio
async def test_draft_prompt_includes_premise_and_full_chapter_target():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None):
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
async def test_draft_prompt_includes_writing_brief_context():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None):
        captured["prompt"] = prompt
        yield "正文"

    svc = AIService()
    svc._stream_ai = fake_stream

    async for _ in svc.draft_assist_stream(
        chapter_title="第7章：火戒初醒",
        outline_hook="古戒第一次发烫",
        outline_summary="林炎借古戒感应涅槃火精残息",
        outline_conflict="从怀疑传承到决定冒险",
        outline_highlight="戒中传来焚老第一声叹息",
        outline_foreshadow="焚荒古戒不能完全开启",
        prev_chapter_tail="林炎把戒指握在掌心。",
        world_summary="万火皆有灵性",
        character_summary="林炎（protagonist）",
        memory_summary="",
        existing_content="",
        writing_brief_context="【本章写前 Brief / 激活资产】\n激活道具/法宝：焚荒古戒；消费方式=只出现微弱反应，不完全开启。",
    ):
        pass

    assert "【本章写前 Brief / 激活资产】" in captured["prompt"]
    assert "只出现微弱反应，不完全开启" in captured["prompt"]


@pytest.mark.asyncio
async def test_draft_prompt_includes_continuity_ledger():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None):
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

    async def fake_call(system: str, prompt: str, max_tokens: int = 2048, context=None):
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
    async def fake_call(system: str, prompt: str, max_tokens: int = 2048, context=None):
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
async def test_auto_debrief_extracts_asset_updates_without_replacing_memory():
    captured = {}

    async def fake_call(system: str, prompt: str, max_tokens: int = 2048, context=None):
        captured["prompt"] = prompt
        return """
        {
          "character_updates": [],
          "storyline_updates": [],
          "memory_updates": [
            {
              "memory_type": "event",
              "title": "林炎获得涅槃火精残息",
              "content": "第7章林炎通过焚荒古戒感应并收起涅槃火精残息，这是后续突破的资源线索。",
              "tags": ["林炎", "涅槃火精残息"]
            }
          ],
          "asset_updates": {
            "new_items": [
              {
                "tier": "B",
                "name": "涅槃火精残息",
                "item_type": "material",
                "rarity": "rare",
                "description": "古戒感应到的一缕火精残息。",
                "effects": "可辅助后续突破。",
                "limitations": "本章不能直接炼化完整火精。",
                "current_owner_name": "林炎",
                "story_significance": "作为焚荒古戒苏醒后的第一条资源线索。"
              }
            ]
          },
          "chapter_index": {},
          "summary": "资产与记忆分开记录。"
        }
        """

    svc = AIService()
    svc._call_ai = fake_call

    result = await svc.auto_extract_debrief(
        chapter_content="林炎通过焚荒古戒感应到涅槃火精残息，并将其收入玉瓶。",
        chapter_title="第7章：火戒初醒",
        chapter_number=7,
        character_states=[],
        storylines=[],
    )

    assert "资产表只记录" in captured["prompt"]
    assert "记忆库记录" in captured["prompt"]
    assert result["memory_updates"][0]["title"] == "林炎获得涅槃火精残息"
    assert result["asset_updates"]["new_items"][0]["name"] == "涅槃火精残息"
    assert result["asset_updates"]["new_items"][0]["tier"] == "B"


@pytest.mark.asyncio
async def test_draft_prompt_includes_chapter_index_context():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None):
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
    assert "【章节速查索引输出模板（必须追加在正文结尾）】" in captured["prompt"]
    assert "### ch_章节号（3位补零）　章节标题" in captured["prompt"]


@pytest.mark.asyncio
async def test_gemini_draft_prompt_uses_expanded_story_context():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None):
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        yield "正文"

    svc = AIService(profile="gemini")
    svc._stream_ai = fake_stream

    async for _ in svc.draft_assist_stream(
        chapter_title="第18章：旧誓回响",
        outline_hook="主角看见上一章留下的血印",
        outline_summary="主角必须兑现旧誓并付出代价",
        outline_conflict="从逃避承诺到主动承担",
        outline_highlight="旧誓牵出宗门秘案",
        outline_foreshadow="回收第16章血印伏笔",
        prev_chapter_tail="上一章关键承诺：不得让师姐独自入阵。" + "乙" * 900 + "上一章章末钩子。",
        world_summary="世界深层规则：誓约会反噬违约者。" + "界" * 1200,
        character_summary="师姐状态：重伤但清醒，位置在阵门外。" + "人" * 900,
        memory_summary="第16章血印来自宗门旧案。" + "忆" * 900,
        existing_content="旧稿深层线索：主角袖中藏着半枚血印。" + "甲" * 1200 + "旧稿末尾。",
        premise="读者承诺：每次逆转都必须先付代价。" + "立" * 1200,
        continuity_context="连续性深层约束：师姐不能突然满状态参战。" + "续" * 2000,
        chapter_index_context="第16章索引：血印未回收。" + "索" * 2000,
    ):
        pass

    assert "上一章关键承诺：不得让师姐独自入阵" in captured["prompt"]
    assert "旧稿深层线索：主角袖中藏着半枚血印" in captured["prompt"]
    assert "世界深层规则：誓约会反噬违约者" in captured["prompt"]
    assert "连续性深层约束：师姐不能突然满状态参战" in captured["prompt"]
    assert "第16章索引：血印未回收" in captured["prompt"]
    assert captured["max_tokens"] >= 8192


@pytest.mark.asyncio
async def test_gemini_quality_check_reads_full_chapter_and_continuity_context():
    captured = {}

    async def fake_call(system: str, prompt: str, max_tokens: int = 2048, context=None):
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        return """
        {
          "overall_score": 8,
          "dimensions": {},
          "issues": [],
          "suggestions": [],
          "summary": "连贯性可读。"
        }
        """

    svc = AIService(profile="gemini")
    svc._call_ai = fake_call

    long_chapter = "开头事件。" + "文" * 2600 + "章末关键矛盾：师姐仍在阵门外，主角独自入阵。"
    result = await svc.quality_check(
        chapter_content=long_chapter,
        chapter_title="第18章：旧誓回响",
        memories=["第16章血印来自宗门旧案。" + "忆" * 600],
        settings_summary=["誓约规则：违约者会被血印反噬。" + "设" * 600],
        check_types=["plot", "setting_consistency", "outline_alignment"],
        character_states=["师姐：境界=筑基，位置=阵门外，状态=重伤，已知技能=[剑阵]"],
        storylines_context=["宗门旧案（active）：血印来源尚未公开"],
        power_systems_summary=["修真境界：炼气 > 筑基 > 金丹；突破必须闭关"],
        outline_context="本章必须兑现旧誓，不能让师姐突然参战。",
        continuity_context="连续性账本：师姐不能突然满状态参战。",
        chapter_index_context="第16章索引：血印伏笔未回收。",
    )

    assert result["overall_score"] == 8
    assert "章末关键矛盾：师姐仍在阵门外" in captured["prompt"]
    assert "连续性账本：师姐不能突然满状态参战" in captured["prompt"]
    assert "第16章索引：血印伏笔未回收" in captured["prompt"]
    assert "修真境界：炼气 > 筑基 > 金丹" in captured["prompt"]
    assert captured["max_tokens"] >= 4096


@pytest.mark.asyncio
async def test_gemini_chapter_coherence_uses_full_text_and_project_context():
    captured = {}

    async def fake_call(system: str, prompt: str, max_tokens: int = 2048, context=None):
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        return """
        {
          "title_match_score": 8,
          "continuity_score": 8,
          "overall_score": 8,
          "chapter_evaluations": [],
          "cross_chapter_issues": [],
          "suggestions": [],
          "summary": "连贯。"
        }
        """

    svc = AIService(profile="gemini")
    svc._call_ai = fake_call

    long_content = "开章承诺。" + "章" * 2600 + "末尾事实：主角还不知道魂殿真名。"
    result = await svc.chapter_coherence_check(
        project_title="苍穹丹祖",
        chapters=[
            {"id": "c1", "sort_order": 0, "title": "第1章", "content": long_content},
            {"id": "c2", "sort_order": 1, "title": "第2章", "content": "主角只看见黑雾，并未听见魂殿二字。"},
        ],
        project_context="项目事实：魂殿真名尚未公开，角色不得凭空知道。",
    )

    assert result["overall_score"] == 8
    assert "末尾事实：主角还不知道魂殿真名" in captured["prompt"]
    assert "项目事实：魂殿真名尚未公开" in captured["prompt"]
    assert captured["max_tokens"] >= 8192
