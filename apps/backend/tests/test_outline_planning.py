from app.services.outline_planning import (
    MIN_CHAPTERS_PER_VOLUME,
    TARGET_CHAPTERS_PER_VOLUME,
    TARGET_WORDS_PER_CHAPTER,
    WORD_ESTIMATE_RANGE,
    chunk_by_volume,
    normalize_chapter_count,
    normalize_volume_plan,
    target_total_chapters,
)
import json

from app.routers.outline import (
    _apply_outline_patch_to_node,
    _detect_outline_hard_rule_issues,
    _format_book_quality_continuity_state,
    _format_outline_batch_goal,
    _format_outline_quality_label,
    _format_outline_quality_story_bible,
    _format_previous_chapters_context,
    _format_rolling_continuity_state,
    _merge_outline_quality_reports,
    _outline_batch_size,
    _outline_quality_nodes_for_scope,
    _outline_node_to_chapter_context,
    _outline_snapshot_payload,
    _sse_outline_quality_progress,
    _with_outline_quality,
)
from app.models.character import Character
from app.models.faction import Faction
from app.models.foreshadow import Foreshadow
from app.models.item import Item
from app.models.outline import OutlineNode
from app.models.power_system import PowerSystem
from app.models.project import Project
from app.models.storyline import StoryLine
from app.models.world_setting import WorldSetting


def test_normalize_chapter_count_rounds_to_thirty_chapter_units():
    assert normalize_chapter_count(15) == MIN_CHAPTERS_PER_VOLUME
    assert normalize_chapter_count(44) == MIN_CHAPTERS_PER_VOLUME
    assert normalize_chapter_count(45) == 60
    assert normalize_chapter_count(46) == 60
    assert normalize_chapter_count(75) == 90
    assert normalize_chapter_count(None) == MIN_CHAPTERS_PER_VOLUME


def test_scale_targets_match_long_novel_word_counts():
    assert TARGET_WORDS_PER_CHAPTER == 2300
    assert WORD_ESTIMATE_RANGE == (2200, 2400)
    assert target_total_chapters("micro") == 180
    assert target_total_chapters("short") == 360
    assert target_total_chapters("auto") == 540
    assert target_total_chapters("medium") == 540
    assert target_total_chapters("long") == 660
    assert target_total_chapters("epic") == 870


def test_medium_plan_is_lifted_to_nine_sixty_chapter_volumes():
    volumes = [{"title": "试炼", "planned_chapters": 15}]

    normalized = normalize_volume_plan(volumes, "medium")

    assert len(normalized) == 9
    assert sum(v["planned_chapters"] for v in normalized) == 540
    assert {v["planned_chapters"] for v in normalized} == {TARGET_CHAPTERS_PER_VOLUME}
    assert normalized[0]["title"] == "试炼（一）"
    assert volumes == [{"title": "试炼", "planned_chapters": 15}]


def test_long_plan_preserves_existing_large_plan():
    volumes = [
        {"title": "入局", "planned_chapters": 300},
        {"title": "破局", "planned_chapters": 360},
    ]

    normalized = normalize_volume_plan(volumes, "long")

    assert len(normalized) == 11
    assert sum(v["planned_chapters"] for v in normalized) == 660
    assert {v["planned_chapters"] for v in normalized} == {TARGET_CHAPTERS_PER_VOLUME}


def test_chunk_by_volume_splits_chapters_into_sixty_chapter_groups():
    chapters = list(range(65))

    groups = list(chunk_by_volume(chapters))

    assert [len(group) for group in groups] == [60, 5]


def test_gemini_outline_generation_uses_stable_large_batches():
    assert _outline_batch_size("gemini") == 30
    assert _outline_batch_size("default") == 15


def test_previous_chapters_context_keeps_recent_batch_continuity_fields():
    chapters = [
        {
            "number": 14,
            "title": "丹火疑云",
            "core_event": "萧炎发现黑雾残痕",
            "character_change": "萧炎从防守转为追查",
            "foreshadow": "埋[黑雾源头] 收[丹火异动]",
            "end_hook": "丹虚子说黑雾来自魂殿",
        },
        {
            "number": 15,
            "title": "旧案之门",
            "core_event": "黑雾线索指向萧家旧案",
            "character_change": "萧炎决定回萧家查证",
            "foreshadow": "埋[萧家旧案真凶]",
            "end_hook": "祠堂石门自行开启",
        },
    ]

    context = _format_previous_chapters_context(chapters, max_items=1)

    assert "第15章：旧案之门" in context
    assert "黑雾线索指向萧家旧案" in context
    assert "祠堂石门自行开启" in context
    assert "第14章" not in context


def test_rolling_continuity_state_extracts_last_hook_and_foreshadows():
    chapters = [
        {
            "number": 15,
            "title": "旧案之门",
            "core_event": "黑雾线索指向萧家旧案",
            "character_change": "萧炎决定回萧家查证",
            "foreshadow": "埋[萧家旧案真凶]",
            "end_hook": "祠堂石门自行开启",
        }
    ]

    state = _format_rolling_continuity_state(chapters)

    assert "上一批最后章节：第15章《旧案之门》" in state
    assert "下一批开篇必须承接：祠堂石门自行开启" in state
    assert "未回收/待处理伏笔：埋[萧家旧案真凶]" in state
    assert "不得重复已发生的核心事件：黑雾线索指向萧家旧案" in state


def test_book_quality_continuity_state_does_not_treat_target_outline_as_history():
    state = _format_book_quality_continuity_state([
        {
            "number": 55,
            "title": "帝都暗门",
            "core_event": "林北辰潜入学院藏经阁。",
            "end_hook": "玺尊塔巨眼睁开。",
        }
    ])

    assert "全书质检不使用滚动连续性账本" in state
    assert "林北辰潜入学院藏经阁" not in state
    assert "不得重复已发生的核心事件" not in state


def test_outline_batch_goal_names_global_and_local_ranges():
    goal = _format_outline_batch_goal(
        node_title="黑雾初临",
        batch_offset=15,
        batch_count=15,
        planned_chapters=60,
    )

    assert "全书第16-30章" in goal
    assert "本卷第16-30章" in goal
    assert "《黑雾初临》共60章" in goal


def test_outline_snapshot_payload_preserves_tree_and_version_fields():
    volume = OutlineNode(
        id="00000000-0000-0000-0000-000000000101",
        node_type="volume",
        title="第一卷",
        summary="边城起势",
        hook="玺尊塔巨眼",
        conflict="皇权压迫",
        sort_order=0,
        extra={"theme_stage": "自强"},
    )
    chapter = OutlineNode(
        id="00000000-0000-0000-0000-000000000102",
        parent_id=volume.id,
        node_type="chapter_plan",
        title="第55章：帝都暗门",
        summary="林北辰潜入学院藏经阁。",
        hook="特赦令失效。",
        conflict="从硬闯转为暗查。",
        highlight="发现九龙玺阴谋。",
        sort_order=54,
        extra={"foreshadow": "埋[九龙玺阴谋]", "end_hook": "巨眼睁开"},
    )

    payload = _outline_snapshot_payload([chapter, volume])

    assert payload["schema_version"] == 1
    assert [n["title"] for n in payload["nodes"]] == ["第一卷", "第55章：帝都暗门"]
    assert payload["nodes"][0]["extra"]["theme_stage"] == "自强"
    assert payload["nodes"][1]["extra"]["end_hook"] == "巨眼睁开"
    assert payload["nodes"][1]["parent_id"] == str(volume.id)


def test_apply_outline_patch_to_node_preserves_before_and_updates_plan_fields():
    node = OutlineNode(
        node_type="chapter_plan",
        title="第55章：旧计划",
        summary="重复硬刚玺尊塔。",
        hook="旧开篇",
        conflict="旧变化",
        highlight="旧钩子",
        sort_order=54,
        extra={"foreshadow": "旧伏笔", "end_hook": "旧钩子"},
    )
    patch = {
        "chapter_number": 55,
        "fields": {
            "opening_hook": "洛红烟递来特赦令。",
            "core_event": "林北辰潜入学院藏经阁。",
            "character_change": "林北辰从硬闯转为暗查。",
            "foreshadow": "埋[九龙玺深层阴谋]",
            "end_hook": "藏经阁最深处的九龙玺拓本睁开巨眼。",
        },
        "reason": "避开卷尾复读，转入调查线。",
    }

    record = _apply_outline_patch_to_node(node, patch)

    assert node.hook == "洛红烟递来特赦令。"
    assert node.summary == "林北辰潜入学院藏经阁。"
    assert node.conflict == "林北辰从硬闯转为暗查。"
    assert node.extra["foreshadow"] == "埋[九龙玺深层阴谋]"
    assert node.extra["end_hook"] == "藏经阁最深处的九龙玺拓本睁开巨眼。"
    assert record["before"]["core_event"] == "重复硬刚玺尊塔。"
    assert record["after"]["core_event"] == "林北辰潜入学院藏经阁。"
    assert record["reason"] == "避开卷尾复读，转入调查线。"


def test_sse_outline_quality_progress_embeds_report_and_unique_progress_key():
    line = _sse_outline_quality_progress(
        step=2,
        total_steps=5,
        label="《卷》卷内质检完成：8分 / pass",
        scope="volume",
        progress_key_suffix="abc",
        report={"overall_score": 8, "status": "pass"},
        done=True,
        error=False,
    )
    raw = line.replace("data: ", "").strip()
    data = json.loads(raw)
    assert data["event"] == "progress"
    assert data["progress_key"] == "2-outline-quality-volume-abc"
    assert data["outline_quality_scope"] == "volume"
    assert data["outline_quality_report"]["overall_score"] == 8


def test_outline_quality_label_summarizes_score_and_must_fix_chapters():
    label = _format_outline_quality_label(
        "黑雾初临",
        {
            "overall_score": 78,
            "status": "warning",
            "must_fix_chapter_numbers": [16, 22],
        },
        scope="volume",
    )

    assert "《黑雾初临》卷内质检完成" in label
    assert "78" in label
    assert "warning" in label
    assert "必修章节：16、22" in label


def test_with_outline_quality_preserves_existing_volume_extra_fields():
    node = OutlineNode(
        node_type="volume",
        title="黑雾初临",
        extra={
            "theme_stage": "主角重新站起来",
            "target_chapters": 60,
        },
    )
    report = {"scope": "volume", "overall_score": 88}

    extra = _with_outline_quality(node, report)

    assert extra["theme_stage"] == "主角重新站起来"
    assert extra["target_chapters"] == 60
    assert extra["outline_quality"] == report


def test_outline_quality_graph_scope_splits_volume_and_book_llm_nodes():
    assert [node.key for node in _outline_quality_nodes_for_scope("volume")] == [
        "prepare_outline_context",
        "quality_check_volumes",
    ]
    assert [node.key for node in _outline_quality_nodes_for_scope("book")] == [
        "prepare_outline_context",
        "quality_check_book",
    ]
    assert [node.key for node in _outline_quality_nodes_for_scope("all")] == [
        "prepare_outline_context",
        "quality_check_volumes",
        "quality_check_book",
    ]


def test_outline_quality_story_bible_collects_world_and_arc_constraints():
    project = Project(
        title="天门逆玺",
        premise="莫欺少年穷；众生平等，打破血缘枷锁。",
        world_overview="天门会周期性收割诸界气运。",
        story_core={"theme": "人族自强而非血统宿命"},
    )
    settings = [
        WorldSetting(
            title="九龙玺规则",
            content="九龙玺最初象征林家正统自强，后来曾被天苍大帝扭曲为寄生引子。",
            tags=["核心道具", "世界规则"],
        )
    ]
    characters = [
        Character(
            name="三皇子",
            role="antagonist",
            current_status="dead",
            current_realm="半步大帝",
            arc="第88章陨落后只能通过转生嫡长子或禁忌傀儡影响剧情。",
        ),
        Character(
            name="苏清月",
            role="supporting",
            current_status="alive",
            arc="第114章完成自我神性初步融合，转为逆天军情报核心。",
            arc_stages=[{"chapter_range": "114-150", "stage": "文职领袖"}],
        ),
    ]
    storylines = [
        StoryLine(
            name="主线：众生平等",
            line_type="main",
            status="active",
            core_conflict="天苍大帝以血统正统垄断成圣资格。",
            resolution_direction="林北辰重塑九龙玺为人族圣物。",
        )
    ]
    power_systems = [
        PowerSystem(
            name="混沌刻印师",
            description="以混沌本源洗练规则刻印。",
            breakthrough_condition="必须承担众生因果。",
        )
    ]
    factions = [
        Faction(
            name="天苍帝国",
            alignment="antagonist",
            goals="封锁位面资源线，等待天门收割。",
        )
    ]
    items = [
        Item(
            name="林家九龙玺",
            rarity="unique",
            status="intact",
            story_significance="正统自强象征，不应被简单否定为敌方寄生物。",
        )
    ]
    foreshadows = [
        Foreshadow(
            code="F-001",
            title="第一缕星尘",
            description="天门缝隙溢出的星尘提示真正收割者苏醒。",
            status="open",
            priority=5,
            planned_resolve_chapter=181,
        )
    ]

    story_bible = _format_outline_quality_story_bible(
        project=project,
        settings=settings,
        characters=characters,
        storylines=storylines,
        power_systems=power_systems,
        factions=factions,
        items=items,
        foreshadows=foreshadows,
    )

    assert "【作品核心约束】" in story_bible
    assert "莫欺少年穷" in story_bible
    assert "九龙玺最初象征林家正统自强" in story_bible
    assert "三皇子（antagonist）状态=dead" in story_bible
    assert "第88章陨落后只能通过转生嫡长子或禁忌傀儡影响剧情" in story_bible
    assert "苏清月（supporting）状态=alive" in story_bible
    assert "114-150:文职领袖" in story_bible
    assert "主线：众生平等（main/active）" in story_bible
    assert "混沌刻印师" in story_bible
    assert "天苍帝国（antagonist）" in story_bible
    assert "林家九龙玺（unique/intact）" in story_bible
    assert "F-001：第一缕星尘" in story_bible


def test_outline_hard_rules_detect_exact_mirrored_endings():
    chapters = [
        {
            "number": 150,
            "title": "碎玺终局",
            "core_event": "林北辰击败三皇子，碎裂九龙玺，天门关闭。",
            "character_change": "林北辰从复仇者转为人族守门人。",
            "end_hook": "全书终。",
        },
        {
            "number": 180,
            "title": "碎玺终局",
            "core_event": "林北辰击败三皇子，碎裂九龙玺，天门关闭。",
            "character_change": "林北辰从复仇者转为人族守门人。",
            "end_hook": "全书终。",
        },
    ]

    report = _detect_outline_hard_rule_issues(chapters)

    assert report["status"] == "fail"
    assert report["overall_score"] == 55
    assert report["must_fix_chapter_numbers"] == [150, 180]
    assert report["issues"][0]["severity"] == "critical"
    assert report["issues"][0]["type"] == "duplicate_event"
    assert report["issues"][0]["chapter_numbers"] == [150, 180]
    assert "核心事件、人物变化、章末钩子完全一致" in report["issues"][0]["description"]


def test_outline_quality_report_merge_prepends_hard_rule_issues_and_caps_score():
    ai_report = {
        "scope": "book",
        "overall_score": 78,
        "status": "warning",
        "summary": "模型发现节奏问题。",
        "issues": [
            {
                "severity": "medium",
                "type": "pacing",
                "chapter_numbers": [121],
                "description": "卷首节奏拖沓。",
            }
        ],
        "must_fix_chapter_numbers": [121],
        "strengths": ["混沌刻印师设定连贯"],
    }
    hard_report = {
        "overall_score": 55,
        "status": "fail",
        "summary": "硬规则发现 1 个确定性结构问题。",
        "issues": [
            {
                "severity": "critical",
                "type": "duplicate_event",
                "chapter_numbers": [150, 180],
                "description": "第150章与第180章镜像重复。",
            }
        ],
        "must_fix_chapter_numbers": [150, 180],
    }

    merged = _merge_outline_quality_reports(ai_report, hard_report)

    assert merged["status"] == "fail"
    assert merged["overall_score"] == 55
    assert merged["issues"][0]["type"] == "duplicate_event"
    assert merged["issues"][1]["type"] == "pacing"
    assert merged["must_fix_chapter_numbers"] == [121, 150, 180]
    assert "硬规则发现 1 个确定性结构问题" in merged["summary"]


def test_outline_node_to_chapter_context_preserves_existing_plan_fields():
    node = OutlineNode(
        node_type="chapter_plan",
        title="第61章：祠堂黑门",
        summary="萧炎推开祠堂石门，发现黑雾祭坛。",
        hook="石门上的血字突然亮起。",
        highlight="丹虚子认出魂殿祭纹。",
        conflict="萧炎从追查旧案变成直面家族秘密。",
        sort_order=60,
        extra={
            "foreshadow": "埋[黑雾祭坛主人] 收[祠堂石门]",
            "end_hook": "祭坛深处传来萧家先祖的声音。",
        },
    )

    context = _outline_node_to_chapter_context(node)

    assert context == {
        "number": 61,
        "title": "祠堂黑门",
        "core_event": "萧炎推开祠堂石门，发现黑雾祭坛。",
        "opening_hook": "石门上的血字突然亮起。",
        "character_change": "萧炎从追查旧案变成直面家族秘密。",
        "foreshadow": "埋[黑雾祭坛主人] 收[祠堂石门]",
        "end_hook": "祭坛深处传来萧家先祖的声音。",
        "pacing": "medium",
        "word_estimate": TARGET_WORDS_PER_CHAPTER,
    }
