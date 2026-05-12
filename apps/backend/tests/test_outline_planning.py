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
import uuid

from app.routers.outline.helpers_core import (
    build_protagonist_realm_timeline,
    merge_outline_and_debrief_realm_milestones,
    _build_realm_rank_map,
    _apply_outline_patch_to_node,
    _detect_outline_embedding_duplicates,
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
    _sanitize_generated_outline_chapter,
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


def test_build_protagonist_realm_timeline_milestones_from_character_change():
    ps = PowerSystem(
        name="修真",
        project_id=uuid.uuid4(),
        levels=[
            {"rank": 1, "name": "感灵境"},
            {"rank": 2, "name": "拓纹境"},
        ],
    )
    chapters = [
        {"number": 1, "title": "开局", "character_change": "林烬以感灵境登记造册。"},
        {"number": 2, "title": "日常", "character_change": "林烬巩固心境，未涉突破。"},
        {"number": 10, "title": "突破", "character_change": "林烬一举突破至拓纹境圆满。"},
    ]
    out = build_protagonist_realm_timeline(chapters, [ps], protagonist_names=["林烬"])
    assert out["has_realm_whitelist"] is True
    assert out["chapter_plans_scanned"] == 3
    assert len(out["milestones"]) == 2
    assert out["milestones"][0]["chapter_number"] == 1
    assert out["milestones"][0]["realm_rank"] == 1
    assert "感灵境" in out["milestones"][0]["realm_name"]
    assert out["milestones"][1]["chapter_number"] == 10
    assert out["milestones"][1]["realm_rank"] == 2


def test_build_protagonist_realm_timeline_empty_without_power_levels():
    ps = PowerSystem(name="空体系", project_id=uuid.uuid4(), levels=[])
    out = build_protagonist_realm_timeline(
        [{"number": 1, "character_change": "林烬突破"}],
        [ps],
        protagonist_names=["林烬"],
    )
    assert out["has_realm_whitelist"] is False
    assert out["milestones"] == []


def test_merge_realm_timeline_combines_outline_and_debrief():
    ps = PowerSystem(
        name="修真",
        project_id=uuid.uuid4(),
        levels=[
            {"rank": 1, "name": "感灵境"},
            {"rank": 2, "name": "拓纹境"},
            {"rank": 3, "name": "凝旋境"},
        ],
    )
    name_to_rank, _, _ = _build_realm_rank_map([ps])
    outline_ms = [
        {
            "chapter_number": 10,
            "chapter_title": "卷末",
            "realm_name": "拓纹境",
            "realm_rank": 2,
            "character_change": "林烬突破至拓纹境。",
        },
    ]
    debrief = [
        {
            "chapter_number": 5,
            "chapter_title": "第五章",
            "realm_name": "感灵境",
            "realm_rank": 1,
            "source": "chapter_debrief",
        },
        {
            "chapter_number": 12,
            "chapter_title": "十二章",
            "realm_name": "凝旋境",
            "realm_rank": 3,
            "source": "chapter_debrief",
        },
    ]
    merged = merge_outline_and_debrief_realm_milestones(outline_ms, debrief, name_to_rank)
    assert [m["chapter_number"] for m in merged] == [5, 10, 12]
    assert merged[0]["source"] == "debrief"
    assert merged[1]["source"] == "outline"
    assert merged[2]["source"] == "debrief"


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


def test_sanitize_generated_outline_chapter_for_xuanhuan_genre():
    chapter = {
        "number": 161,
        "title": "神渊枢纽：AI回响",
        "opening_hook": "控制台上的程序上传进度突然跳动。",
        "core_event": "林北辰遭遇半机械守卫，发现芯片里封印的记忆。",
        "character_change": "他意识到父亲并非首席工程师，而是被AI化的囚徒。",
        "foreshadow": "埋[量子密钥] 收[星际文明遗迹]",
        "end_hook": "基因实验室深处传来熟悉的呼喊。",
    }

    cleaned = _sanitize_generated_outline_chapter(chapter, "玄幻")

    assert "首席工程师" not in cleaned["character_change"]
    assert "AI化" not in cleaned["character_change"]
    assert "半机械" not in cleaned["core_event"]
    assert "芯片" not in cleaned["core_event"]
    assert "控制台" not in cleaned["opening_hook"]
    assert "程序上传" not in cleaned["opening_hook"]
    assert "量子" not in cleaned["foreshadow"]
    assert "星际文明" not in cleaned["foreshadow"]
    assert "基因实验室" not in cleaned["end_hook"]


# ─────────────────────────────────────────────────────────────
#  Hard rule sub-checks: terminology + power curve
# ─────────────────────────────────────────────────────────────

def _ling_wen_power_system() -> PowerSystem:
    """模拟当前项目使用的「灵纹体系」(感灵→拓纹→凝旋→归墟→大荒→灵王) 5 级。"""
    system = PowerSystem(
        name="灵纹体系",
        levels=[
            {"rank": 1, "name": "感灵境"},
            {"rank": 2, "name": "拓纹境"},
            {"rank": 3, "name": "凝旋境"},
            {"rank": 4, "name": "归墟境"},
            {"rank": 5, "name": "大荒境"},
            {"rank": 6, "name": "灵王境"},
        ],
        protagonist_end_rank=8,
    )
    return system


def test_hard_rule_backward_compat_only_duplicate_check_when_no_power_systems():
    """旧调用方式（不传 power_systems）必须保持原行为：单一 critical duplicate → 55 分。"""
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
    assert len(report["issues"]) == 1
    assert report["issues"][0]["type"] == "duplicate_event"


def test_hard_rule_terminology_blacklist_flags_zhujidan_when_system_uses_ling_wen():
    """项目用「灵纹体系」时，章节出现「筑基」「金丹」必须被判 critical。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": 8,
            "title": "破障筑基",
            "core_event": "林烬冲破筑基瓶颈，体内金丹初成。",
            "character_change": "林烬从感灵境跨入筑基境。",
            "foreshadow": "埋[筑基灵根]",
            "end_hook": "丹田之中金丹隐现。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",
    )
    assert report["status"] == "fail"
    assert report["overall_score"] == 55
    assert 8 in report["must_fix_chapter_numbers"]
    issue_types = [issue["type"] for issue in report["issues"]]
    assert "continuity" in issue_types
    cultivation_issue = next(
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "修真术语" in issue["description"]
    )
    assert "筑基" in cultivation_issue["description"]
    assert "金丹" in cultivation_issue["description"]


def test_hard_rule_terminology_allows_custom_realm_names_in_whitelist():
    """合法的项目自定义境界（拓纹/凝旋/大荒）必须 100 分通过。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": 8,
            "title": "破障拓纹",
            "core_event": "林烬冲破桎梏，跨入拓纹境一重。",
            "character_change": "林烬从感灵境晋升拓纹境一重，天墟之火进化出破障属性。",
            "foreshadow": "埋[拓纹境异变]",
            "end_hook": "天墟之火第一次焚穿敌方灵纹防御。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",
    )
    assert report["status"] == "pass"
    assert report["overall_score"] == 100
    assert report["issues"] == []


def test_hard_rule_terminology_modern_words_under_xuanhuan_genre():
    """玄幻题材下出现 AI/芯片/量子 等现代词必须 critical。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": 12,
            "title": "圣塔机关",
            "core_event": "林烬潜入圣塔，发现古老芯片中封存的人工智能残识。",
            "character_change": "林烬意识到圣塔本质是上古量子阵法。",
            "foreshadow": "埋[AI傀儡]",
            "end_hook": "芯片骤然过载。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="东方玄幻",
        scope="volume",
    )
    assert report["status"] == "fail"
    assert report["overall_score"] == 55
    modern_issue = next(
        issue for issue in report["issues"]
        if "现代/科幻词汇" in issue["description"]
    )
    assert "AI" in modern_issue["description"] or "芯片" in modern_issue["description"]


def test_hard_rule_power_curve_realm_regression_without_trigger_flagged():
    """主角 character_change 中境界回落 ≥2 级且无代价说明 → high。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": 40,
            "title": "凝旋之巅",
            "core_event": "林烬一战封神。",
            "character_change": "林烬突破至凝旋境圆满。",
            "end_hook": "万火阁震动。",
        },
        {
            "number": 57,
            "title": "入门测试",
            "core_event": "万火阁外门考核。",
            "character_change": "林烬以感灵境身份参加外门考核。",
            "end_hook": "考核官冷笑。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",
    )
    assert report["status"] == "fail"
    regression_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "境界倒退" in issue["description"]
    ]
    assert len(regression_issues) >= 1
    assert 57 in report["must_fix_chapter_numbers"]


def test_hard_rule_power_curve_regression_allowed_with_trigger_word():
    """character_change 中说明了「重伤/透支/跌落」时不应触发回退告警。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": 40,
            "title": "凝旋之巅",
            "core_event": "林烬一战封神。",
            "character_change": "林烬突破至凝旋境圆满。",
            "end_hook": "万火阁震动。",
        },
        {
            "number": 46,
            "title": "透支寿元",
            "core_event": "林烬强行斩杀圣塔特使。",
            "character_change": (
                "林烬透支寿元，境界跌落回拓纹境初期，急需万火阁资源疗伤。"
            ),
            "end_hook": "他咳出一口黑血。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",
    )
    regression_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "境界倒退" in issue["description"]
    ]
    assert regression_issues == []


def test_hard_rule_power_curve_no_false_positive_npc_realm_with_protagonist_card():
    """已配置主角人物卡时，见闻/敌方的高阶境界不得抬高 running_max，避免第4/6/12章类假阳性。"""
    system = _ling_wen_power_system()
    lin = Character(name="林烬", role="protagonist")
    chapters = [
        {
            "number": 4,
            "title": "余波",
            "core_event": "古战场残留灵压爆发。",
            "character_change": "林烬亲历灵王境强者交手余波，愈发认清自身与顶尖梯队差距。",
            "end_hook": "风沙里传来冷笑。",
        },
        {
            "number": 6,
            "title": "入门",
            "core_event": "外门登记。",
            "character_change": "林烬以感灵境身份登记造册，暂隐锋芒。",
            "end_hook": "执事抬眼打量。",
        },
        {
            "number": 12,
            "title": "拓路",
            "core_event": "夜路遇袭。",
            "character_change": "林烬巩固拓纹境根基，刀意更凝练一分。",
            "end_hook": "远处火光一闪。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",
        characters=[lin],
    )
    regression_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "境界倒退" in issue.get("description", "")
    ]
    assert regression_issues == []


def test_hard_rule_power_curve_book_pacing_collapse_when_peak_too_early():
    """书级范围：211/360 章已达终点境界，剩余 41% 章节 → high pacing。"""
    system = _ling_wen_power_system()
    # 211 章登顶大荒境（rank 5），系统 max_rank=6，protagonist_end_rank=8 → 211 章 rank>=8 才算到顶。
    # 这里改用直接登顶到 rank 8 的设定：把 system 末级改成 rank 8。
    system.levels = [
        *system.levels,
        {"rank": 7, "name": "天罡境"},
        {"rank": 8, "name": "圣君境"},
    ]
    chapters = []
    for n in range(1, 211):
        chapters.append({
            "number": n,
            "title": f"过场{n}",
            "core_event": f"事件{n}",
            "character_change": "",
            "end_hook": "下一章再说。",
        })
    chapters.append({
        "number": 211,
        "title": "登顶圣君",
        "core_event": "林烬斩杀圣地少主，收齐四朵异火。",
        "character_change": "林烬一举突破至圣君境圆满，已抵全书规划终点。",
        "end_hook": "上界裂缝中，神光大盛。",
    })
    for n in range(212, 361):
        chapters.append({
            "number": n,
            "title": f"过场{n}",
            "core_event": f"事件{n}",
            "character_change": "",
            "end_hook": "继续。",
        })
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="book",
    )
    pacing_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "pacing"
    ]
    assert len(pacing_issues) == 1
    assert pacing_issues[0]["severity"] == "high"
    assert pacing_issues[0]["chapter_numbers"] == [211]
    assert "剩余" in pacing_issues[0]["description"]


def test_hard_rule_power_curve_pacing_only_fires_at_book_scope():
    """卷级范围内即使主角到顶也不应触发 end-of-book pacing 告警。"""
    system = _ling_wen_power_system()
    chapters = [
        {
            "number": i,
            "title": f"卷内{i}",
            "core_event": "凝聚灵纹。",
            "character_change": "林烬向灵王境推进。" if i == 30 else "",
            "end_hook": "继续修炼。",
        }
        for i in range(1, 61)
    ]
    chapters[29]["character_change"] = "林烬一举突破至灵王境圆满。"
    report = _detect_outline_hard_rule_issues(
        chapters,
        power_systems=[system],
        genre="玄幻",
        scope="volume",  # 卷级
    )
    pacing_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "pacing"
    ]
    assert pacing_issues == []


# ─────────────────────────────────────────────────────────────
#  Character death continuity sub-check
# ─────────────────────────────────────────────────────────────

def _gui_shou_character() -> Character:
    return Character(name="鬼手", alias=["鬼手长老", "断手前辈"])


def test_hard_rule_character_death_flags_active_reappearance_without_revival():
    """鬼手 110 章自毁，但 123/145/158 章持续提供道具/出手，且无复活说明 → critical。"""
    char = _gui_shou_character()
    chapters = [
        {
            "number": 110,
            "title": "归墟自毁",
            "core_event": "鬼手为掩护林烬撤离，启动自毁阵法，与圣塔先遣军同归于尽。",
            "character_change": "鬼手身死，林烬失去最后的师长。",
            "end_hook": "归墟铜钱滚落在血泊中。",
        },
        {
            "number": 123,
            "title": "黑市再会",
            "core_event": "黑市深夜，鬼手送来一枚归墟符。",
            "character_change": "林烬意外重获援助。",
            "end_hook": "鬼手的身影一闪而逝。",
        },
        {
            "number": 145,
            "title": "鬼手出手",
            "core_event": "陷入重围之时，鬼手出手解围。",
            "character_change": "众人惊愕。",
            "end_hook": "鬼手转身远去。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        characters=[char],
    )
    assert report["status"] == "fail"
    assert report["overall_score"] == 55
    death_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "生死逻辑断层" in issue["description"]
    ]
    assert len(death_issues) >= 2
    flagged_chapters = sorted({
        issue["chapter_numbers"][1] for issue in death_issues
        if len(issue.get("chapter_numbers", [])) >= 2
    })
    assert 123 in flagged_chapters
    assert 145 in flagged_chapters


def test_hard_rule_character_death_skipped_with_revival_mechanism():
    """死后若交代了「神魂寄宿/化身/残识」等机制，再次出场不应告警。"""
    char = _gui_shou_character()
    chapters = [
        {
            "number": 110,
            "title": "归墟自毁",
            "core_event": "鬼手为掩护林烬撤离，启动自毁阵法，与圣塔先遣军同归于尽。",
            "character_change": "鬼手身殒，神魂寄宿于归墟铜钱中。",
            "end_hook": "铜钱微微震颤。",
        },
        {
            "number": 123,
            "title": "铜钱回响",
            "core_event": "归墟铜钱中的鬼手残识苏醒，向林烬传授残篇。",
            "character_change": "林烬感受到鬼手的意志依然在引路。",
            "end_hook": "传承之火点燃。",
        },
        {
            "number": 145,
            "title": "化身出手",
            "core_event": "鬼手以分身化身介入大战。",
            "character_change": "林烬终于明白前路。",
            "end_hook": "化身转身远去。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        characters=[char],
    )
    death_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "生死逻辑断层" in issue["description"]
    ]
    assert death_issues == []


def test_hard_rule_character_death_uses_alias_for_matching():
    """别名（鬼手长老/断手前辈）也要参与匹配。"""
    char = _gui_shou_character()
    chapters = [
        {
            "number": 110,
            "title": "断手殒落",
            "core_event": "断手前辈舍身护道，自毁阵法启动。",
            "character_change": "众人沉默。",
            "end_hook": "灰烬飘散。",
        },
        {
            "number": 130,
            "title": "黑市偶遇",
            "core_event": "鬼手长老送来一枚护身符。",
            "character_change": "林烬不解。",
            "end_hook": "护身符温热。",
        },
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        characters=[char],
    )
    death_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "生死逻辑断层" in issue["description"]
    ]
    assert len(death_issues) == 1
    assert death_issues[0]["chapter_numbers"] == [110, 130]


def test_hard_rule_character_death_skipped_when_no_characters_param():
    """不传 characters 时跳过该检查（向后兼容）。"""
    chapters = [
        {
            "number": 110,
            "title": "鬼手殒落",
            "core_event": "鬼手自毁同归于尽。",
            "character_change": "鬼手身死。",
            "end_hook": "灰烬飘散。",
        },
        {
            "number": 130,
            "title": "鬼手现身",
            "core_event": "鬼手送来护身符。",
            "character_change": "林烬不解。",
            "end_hook": "护身符温热。",
        },
    ]
    report = _detect_outline_hard_rule_issues(chapters)
    assert report["status"] == "pass"
    assert report["issues"] == []


# ─────────────────────────────────────────────────────────────
#  Embedding-based semantic duplicate detection (pure function)
# ─────────────────────────────────────────────────────────────

def test_embedding_duplicates_detect_high_cosine_in_volume_scope():
    """两章向量近乎一致（cosine ≈ 1）→ high 软重复。"""
    chapters = [
        {"number": 149, "title": "圣坛救妹", "core_event": "林烬劈开圣坛大门救林梦。",
         "character_change": "林烬怒火中烧。", "end_hook": "林梦的眼神变了。"},
        {"number": 169, "title": "夺回林梦", "core_event": "林烬再战圣坛终极博弈。",
         "character_change": "林烬决意一搏。", "end_hook": "林梦的灵魂动摇。"},
    ]
    vectors = {
        149: [1.0, 0.0, 0.0, 0.0],
        169: [0.99, 0.10, 0.0, 0.0],  # cosine ≈ 0.995
    }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope="volume")
    assert len(issues) == 1
    assert issues[0]["type"] == "duplicate_event"
    assert issues[0]["severity"] == "high"
    assert issues[0]["chapter_numbers"] == [149, 169]
    assert "语义相似度" in issues[0]["description"]


def test_embedding_duplicates_skip_when_below_medium_threshold():
    """cosine 低于 medium 阈值时不告警。"""
    chapters = [
        {"number": 1, "title": "一", "core_event": "事件A。", "character_change": "", "end_hook": ""},
        {"number": 2, "title": "二", "core_event": "事件B。", "character_change": "", "end_hook": ""},
    ]
    vectors = {
        1: [1.0, 0.0, 0.0, 0.0],
        2: [0.0, 1.0, 0.0, 0.0],   # cosine = 0
    }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope="volume")
    assert issues == []


def test_embedding_duplicates_book_scope_skips_far_apart_chapters():
    """book scope 下跨距 > 60 的对不参与比较。"""
    chapters = [
        {"number": 10, "title": "一", "core_event": "事件A。", "character_change": "", "end_hook": ""},
        {"number": 200, "title": "二", "core_event": "事件A'。", "character_change": "", "end_hook": ""},
    ]
    vectors = {
        10: [1.0, 0.0, 0.0, 0.0],
        200: [0.99, 0.10, 0.0, 0.0],
    }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope="book")
    assert issues == []


def test_embedding_duplicates_medium_severity_triggers_at_lower_cosine():
    """cosine 在 [0.78, 0.85) 区间 → medium 软重复。"""
    chapters = [
        {"number": 1, "title": "一", "core_event": "事件A。", "character_change": "", "end_hook": ""},
        {"number": 2, "title": "二", "core_event": "事件B。", "character_change": "", "end_hook": ""},
    ]
    # 构造 cosine ≈ 0.80 的两个单位向量
    import math
    angle_a = 0.0
    angle_b = math.acos(0.80)
    vectors = {
        1: [math.cos(angle_a), math.sin(angle_a)],
        2: [math.cos(angle_b), math.sin(angle_b)],
    }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope="volume")
    assert len(issues) == 1
    assert issues[0]["severity"] == "medium"


def test_embedding_duplicates_handles_missing_vectors_gracefully():
    """vectors_by_number 为空 → 直接返回空 issues，不抛异常。"""
    chapters = [
        {"number": 1, "title": "一", "core_event": "事件A。", "character_change": "", "end_hook": ""},
        {"number": 2, "title": "二", "core_event": "事件B。", "character_change": "", "end_hook": ""},
    ]
    issues = _detect_outline_embedding_duplicates(chapters, {}, scope="volume")
    assert issues == []


# ─────────────────────────────────────────────────────────────
#  Theme alignment validator
# ─────────────────────────────────────────────────────────────

def test_theme_alignment_flags_perfect_furnace_when_theme_is_caogen():
    """主题为「凡人逆袭/草根」时，揭露主角是「完美炉胎」必须被判 medium。"""
    chapters = [
        {
            "number": 200,
            "title": "炉胎真相",
            "core_event": "圣塔密档曝光：林烬其实是『完美炉胎』实验的终点。",
            "character_change": "林烬意识到自己天生就是被选中。",
            "end_hook": "他陷入沉思。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        theme_statement="我命由我，凡人逆袭",
    )
    theme_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "theme_alignment"
    ]
    assert len(theme_issues) == 1
    assert theme_issues[0]["severity"] == "medium"
    assert 200 in report["must_fix_chapter_numbers"]
    assert "完美炉胎" in theme_issues[0]["description"]


def test_theme_alignment_skipped_when_theme_not_self_determination():
    """主题不属于「自我决定型」时，揭露完美炉胎不告警。"""
    chapters = [
        {
            "number": 200,
            "title": "炉胎真相",
            "core_event": "林烬其实是『完美炉胎』实验的终点。",
            "character_change": "他天生强大。",
            "end_hook": "陷入沉思。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        theme_statement="复仇与权谋的史诗",
    )
    theme_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "theme_alignment"
    ]
    assert theme_issues == []


def test_theme_alignment_requires_protagonist_context():
    """揭露「完美炉胎」但只描述 NPC 时不告警（避免误伤反派/路人设定）。"""
    chapters = [
        {
            "number": 88,
            "title": "敌方真相",
            "core_event": "圣塔少主原来是『完美炉胎』实验产物，难怪天生神力。",
            "character_change": "众弟子哗然。",
            "end_hook": "局势更复杂。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        theme_statement="凡人逆袭，草根崛起",
    )
    theme_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "theme_alignment"
    ]
    assert theme_issues == []


def test_theme_alignment_uses_protagonist_name_as_context():
    """如果 character 表里 protagonist 名字直接出现在揭露上下文，也应触发。"""
    protagonist = Character(name="林烬", role="protagonist")
    chapters = [
        {
            "number": 200,
            "title": "血脉觉醒",
            "core_event": "林烬血脉觉醒，被认证为帝者血脉的最后传人。",
            "character_change": "林烬感受到先天圣体的力量。",
            "end_hook": "他失声。",
        }
    ]
    report = _detect_outline_hard_rule_issues(
        chapters,
        theme_statement="后天突破，凡人也能问鼎巅峰",
        characters=[protagonist],
    )
    theme_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "theme_alignment"
    ]
    assert len(theme_issues) == 1
    assert theme_issues[0]["chapter_numbers"] == [200]


def test_theme_alignment_skipped_when_no_theme_statement():
    """无 theme_statement 时跳过（不可能判定冲突）。"""
    chapters = [
        {
            "number": 200,
            "title": "炉胎真相",
            "core_event": "林烬其实是『完美炉胎』。",
            "character_change": "他是天选之子。",
            "end_hook": "沉思。",
        }
    ]
    report = _detect_outline_hard_rule_issues(chapters)
    theme_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "theme_alignment"
    ]
    assert theme_issues == []


# ─────────────────────────────────────────────────────────────
#  Foreshadow ledger auditor
# ─────────────────────────────────────────────────────────────

def test_foreshadow_audit_flags_overdue_open_resolution():
    """planned_resolve_chapter < 当前最新章 + status=open → high pacing。"""
    chapters = [
        {"number": n, "title": f"chap{n}", "core_event": "", "character_change": "", "end_hook": ""}
        for n in (1, 90, 150)
    ]
    fore = Foreshadow(
        code="F-001",
        title="鬼手真身之谜",
        status="open",
        priority=4,
        laid_chapter_number=20,
        planned_resolve_chapter=80,
    )
    report = _detect_outline_hard_rule_issues(
        chapters,
        foreshadows=[fore],
    )
    overdue_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "pacing" and "已过期未回收" in issue["description"]
    ]
    assert len(overdue_issues) == 1
    assert overdue_issues[0]["severity"] == "high"
    assert overdue_issues[0]["chapter_numbers"] == [80]


def test_foreshadow_audit_flags_long_aged_high_priority_open():
    """priority>=4 + open + 跨度>100 章 → medium pacing（无 planned_resolve_chapter 也触发）。"""
    chapters = [
        {"number": n, "title": f"chap{n}", "core_event": "", "character_change": "", "end_hook": ""}
        for n in (1, 60, 200)
    ]
    fore = Foreshadow(
        code="F-002",
        title="圣塔上层秘密",
        status="open",
        priority=5,
        laid_chapter_number=30,
        planned_resolve_chapter=None,
    )
    report = _detect_outline_hard_rule_issues(
        chapters,
        foreshadows=[fore],
    )
    aged_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "pacing" and "长期挂账" in issue["description"]
    ]
    assert len(aged_issues) == 1
    assert aged_issues[0]["severity"] == "medium"
    assert aged_issues[0]["chapter_numbers"] == [30]


def test_foreshadow_audit_flags_critical_priority_dropped():
    """priority>=5 + status=dropped → high continuity。"""
    chapters = [
        {"number": n, "title": f"chap{n}", "core_event": "", "character_change": "", "end_hook": ""}
        for n in (1, 50, 120)
    ]
    fore = Foreshadow(
        code="F-003",
        title="林家先祖与天墟之火的因果",
        status="dropped",
        priority=5,
        laid_chapter_number=22,
        planned_resolve_chapter=200,
    )
    report = _detect_outline_hard_rule_issues(
        chapters,
        foreshadows=[fore],
    )
    dropped_issues = [
        issue for issue in report["issues"]
        if issue["type"] == "continuity" and "关键主线悬念被丢弃" in issue["description"]
    ]
    assert len(dropped_issues) == 1
    assert dropped_issues[0]["severity"] == "high"


def test_foreshadow_audit_skipped_without_foreshadows_param():
    """不传 foreshadows 时跳过该子检查（向后兼容）。"""
    chapters = [
        {
            "number": 80,
            "title": "未回收",
            "core_event": "正常情节。",
            "character_change": "",
            "end_hook": "",
        }
    ]
    report = _detect_outline_hard_rule_issues(chapters)
    foreshadow_typed_issues = [
        issue for issue in report["issues"]
        if "F-" in issue.get("description", "") or "伏笔" in issue.get("description", "")
    ]
    assert foreshadow_typed_issues == []


def test_foreshadow_audit_resolved_status_does_not_trigger():
    """已 resolved 的伏笔不应触发任何告警，无论是否过期。"""
    chapters = [
        {"number": n, "title": f"chap{n}", "core_event": "", "character_change": "", "end_hook": ""}
        for n in (1, 200)
    ]
    fore = Foreshadow(
        code="F-004",
        title="九幽寒脉觉醒",
        status="resolved",
        priority=5,
        laid_chapter_number=15,
        planned_resolve_chapter=80,
        resolved_chapter_number=85,
    )
    report = _detect_outline_hard_rule_issues(
        chapters,
        foreshadows=[fore],
    )
    fore_issues = [
        issue for issue in report["issues"]
        if "伏笔" in issue.get("description", "") or "F-" in issue.get("description", "")
    ]
    assert fore_issues == []


def test_merge_caps_score_to_lowest_severity_across_multiple_hard_checks():
    """多类硬规则问题合并时，overall_score 取最低分，issues 全部保留。"""
    ai_report = {
        "scope": "book",
        "overall_score": 78,
        "status": "warning",
        "summary": "AI 发现节奏问题。",
        "issues": [{
            "severity": "medium",
            "type": "pacing",
            "chapter_numbers": [121],
            "description": "卷首节奏拖沓。",
        }],
        "must_fix_chapter_numbers": [121],
    }
    hard_report = {
        "overall_score": 55,
        "status": "fail",
        "summary": "硬规则发现 3 个确定性结构问题。",
        "issues": [
            {
                "severity": "critical",
                "type": "continuity",
                "chapter_numbers": [8],
                "description": "第8章使用了项目力量体系外的修真术语：筑基、金丹。",
            },
            {
                "severity": "high",
                "type": "continuity",
                "chapter_numbers": [57],
                "description": "第57章境界倒退无解释。",
            },
            {
                "severity": "high",
                "type": "pacing",
                "chapter_numbers": [211],
                "description": "末段压进过快。",
            },
        ],
        "must_fix_chapter_numbers": [8, 57, 211],
    }
    merged = _merge_outline_quality_reports(ai_report, hard_report)
    assert merged["overall_score"] == 55
    assert merged["status"] == "fail"
    assert merged["must_fix_chapter_numbers"] == [8, 57, 121, 211]
    issue_types = [issue["type"] for issue in merged["issues"]]
    assert issue_types[:3] == ["continuity", "continuity", "pacing"]
    assert "硬规则发现 3 个确定性结构问题" in merged["summary"]
