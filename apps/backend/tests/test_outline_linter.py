"""outline_linter 单测。"""

from app.services.outline_linter.helpers import (
    ChapterSnapshot,
    is_placeholder,
    text_overlap,
)
from app.services.outline_linter.repair_hints import build_repair_seed
from app.services.outline_linter.rules_chapter import lint_chapters
from app.services.outline_linter.rules_sequence import lint_sequence
from app.services.outline_linter.rules_volume import lint_volume
from app.services.outline_linter.schemas import LinterIssue, LinterReport


def _ch(
    num: int,
    *,
    want: str = "主角要夺回宗门信物",
    cost: str = "暴露身份，被通缉",
    hook: str = "通缉令贴满城门，主角不得不藏身",
    end_hook: str = "他在废墟里发现信物上的血指印",
    summary: str = "因潜入禁地，主角被执法队追杀",
    villain: str = "长老暗中调动执法队封锁出口",
    foreshadow: str = "",
    has_slap: bool = False,
    has_beat: bool = False,
    pacing: str = "normal",
    storyline_ids: list | None = None,
) -> ChapterSnapshot:
    return ChapterSnapshot(
        id=f"id-{num}",
        sort_order=num - 1,
        title=f"第{num}章",
        summary=summary,
        hook=hook,
        highlight=end_hook,
        conflict="认知变化",
        pacing=pacing,
        phase="rising",
        expected_words=2300,
        storyline_ids=storyline_ids or ["sl-1"],
        involved_character_ids=["c-1"],
        power_milestone=None,
        extra={
            "protagonist_want": want,
            "protagonist_obstacle": "执法队封锁山门",
            "protagonist_choice": "冒险从暗渠突围",
            "choice_cost": cost,
            "villain_action": villain,
            "end_hook": end_hook,
            "foreshadow": foreshadow,
            "has_face_slap": has_slap,
            "has_emotional_beat": has_beat,
        },
    )


def test_is_placeholder():
    assert is_placeholder("（无）")
    assert not is_placeholder("主角失去左臂")


def test_text_overlap():
    assert text_overlap("被通缉", "通缉令贴满城门")
    assert not text_overlap("abc", "xyz")


def test_ch15_only_flags_under_budget_not_over():
    """预期字数高于阶段预算（如高潮章写长）不应报 CH-15。"""
    ch_short = _ch(1, cost="代价足够长以满足承接检测要求")
    ch_short.expected_words = 1800
    ch_long = _ch(60, cost="代价足够长以满足承接检测要求")
    ch_long.expected_words = 3300
    issues = lint_chapters([ch_short, ch_long])
    assert any(i.rule_id == "CH-15" and i.chapter_number_in_volume == 1 for i in issues)
    assert not any(i.rule_id == "CH-15" and i.chapter_number_in_volume == 60 for i in issues)


def test_ch04_critical_on_empty_cost():
    ch = _ch(1, cost="")
    issues = lint_chapters([ch])
    assert any(i.rule_id == "CH-04" and i.severity == "critical" for i in issues)


def test_seq01_cost_not_carried():
    a = _ch(1, cost="师父为救他战死，宗门令牌碎裂")
    b = _ch(2, hook="全新地图开启，主角参观坊市", summary="主角在坊市购买丹药")
    issues = lint_sequence([a, b], volume_phase="rising", planned_chapters=30)
    assert any(i.rule_id == "SEQ-01" for i in issues)


def test_seq07_only_on_batch_boundaries():
    """整卷单次 50 章时第 31 章不应触发 SEQ-07（仅真实分批边界才阻断）。"""
    ch30 = _ch(30, cost="身份暴露，被迫交出令牌")
    ch31 = _ch(31, hook="全新地图开启，主角参观坊市", summary="主角在坊市购买丹药")
    single_batch = lint_sequence(
        [ch30, ch31],
        volume_phase="rising",
        planned_chapters=50,
        batch_boundary_chapters=set(),
    )
    assert not any(i.rule_id == "SEQ-07" for i in single_batch)

    split_batch = lint_sequence(
        [ch30, ch31],
        volume_phase="rising",
        planned_chapters=50,
        batch_boundary_chapters={31},
    )
    assert any(i.rule_id == "SEQ-07" for i in split_batch)


def test_vl01_count_mismatch():
    chapters = [_ch(i) for i in range(1, 6)]
    issues = lint_volume(
        chapters,
        planned_chapters=30,
        volume_phase="opening",
        pace_type="medium",
        is_first_volume=True,
    )
    assert any(i.rule_id == "VL-01" for i in issues)


def test_vl04_face_slap_window():
    chapters = [_ch(i, has_slap=False) for i in range(1, 9)]
    issues = lint_volume(
        chapters,
        planned_chapters=8,
        volume_phase="rising",
        pace_type="medium",
    )
    assert any(i.rule_id in ("VL-03", "VL-04") for i in issues)


def test_report_finalize_status():
    r = LinterReport()
    r.issues.extend(lint_chapters([_ch(1, cost="")]))
    r.finalize_status()
    assert r.status == "failed"


def test_seq05_semantic_duplicate():
    a = _ch(1, summary="主角潜入禁地夺取信物，被执法队追杀至悬崖", end_hook="崖边发现师兄留下的血书")
    b = _ch(2, summary="主角潜入禁地夺取信物，被执法队追杀至悬崖", end_hook="崖边发现师兄留下的血书")
    from app.services.outline_linter.rules_sequence import lint_semantic_duplicates

    issues = lint_semantic_duplicates([a, b])
    assert any(i.rule_id == "SEQ-05" for i in issues)


def test_report_blocks_commit():
    from app.services.outline_linter.gate import report_blocks_commit
    from app.services.outline_linter.schemas import LinterIssue, LinterReport

    r = LinterReport(issues=[
        LinterIssue(
            rule_id="CH-04", severity="critical", scope="chapter",
            message="x", chapter_number_in_volume=1,
        ),
    ])
    assert report_blocks_commit(r)


def test_vol1_sse_payload_blocked():
    from app.services.outline_linter.sse_payload import build_vol1_chapters_sse_payload

    payload = build_vol1_chapters_sse_payload(
        [],
        {
            "linter_blocked": True,
            "linter_last_report": {
                "status": "failed",
                "issue_count": 5,
                "critical_count": 2,
                "high_count": 1,
                "issues": [
                    {
                        "rule_id": "CH-04",
                        "severity": "critical",
                        "scope": "chapter",
                        "message": "第3章「选择代价」为空或仅占位",
                        "suggestion": "补写代价",
                        "chapter_number_in_volume": 3,
                    },
                    {
                        "rule_id": "VL-01",
                        "severity": "critical",
                        "scope": "volume",
                        "message": "章纲数量 28 与配额 30 不符",
                    },
                ],
            },
        },
    )
    assert payload["count"] == 0
    assert payload["linter_blocked"] is True
    assert "章纲·选择代价" in payload["preview"]
    assert payload["linter_critical_count"] == 2
    assert "选择代价" in payload["linter_message"]
    assert payload["linter_blocking_rules"] == ["CH-04"]
    assert len(payload["linter_issues_top"]) >= 1


def test_build_linter_block_payload_with_draft():
    from app.services.outline_linter.user_facing import build_linter_block_payload

    out = build_linter_block_payload(
        {
            "status": "failed",
            "critical_count": 1,
            "high_count": 0,
            "issue_count": 1,
            "issues": [
                {
                    "rule_id": "CH-08",
                    "severity": "critical",
                    "scope": "chapter",
                    "message": "第1章「核心事件」为空",
                    "chapter_number_in_volume": 1,
                },
            ],
        },
        chapter_count=30,
    )
    assert "草稿" in out["linter_message"]
    assert out["linter_draft_saved"] is True
    assert "核心事件" in out["preview"]
    assert "严重" in out["linter_message"]


def test_promise_fulfilled_in_window():
    from app.services.outline_linter.rules_promises import promise_fulfilled_in_window

    text = "戒指内沉睡三年的陆九渊首次回应叶焚的怒火"
    fulfilled = {2: "陆九渊在戒指中回应，叶焚得知修为消失另有隐情"}
    assert promise_fulfilled_in_window(fulfilled, text, 1, 2)
    assert not promise_fulfilled_in_window({}, text, 1, 2)


def test_rp03_one_issue_per_chapter_when_no_overlap():
    """多条未兑现承诺时，同章仅应报 1 条 RP-03。"""
    from app.services.outline_linter.rules_promises import _rp03_issues_for_chapters

    ch = _ch(28, foreshadow="")
    ch.extra["promise_fulfilled"] = "主角在秘境悟得全新剑意"
    promises = [
        ("大比前坊市发现神火残图", 4),
        ("戒指内陆九渊首次回应", 4),
        ("叶焚立下三年复仇之约", 3),
    ]
    issues = _rp03_issues_for_chapters([ch], promises)
    assert len(issues) == 1
    assert issues[0].rule_id == "RP-03"
    assert issues[0].chapter_number_in_volume == 28
    assert "第28章" in issues[0].message
    assert "本章兑现承诺" in issues[0].message
    assert "全新剑意" in issues[0].message


def test_rp03_no_issue_when_keyword_overlaps():
    from app.services.outline_linter.rules_promises import _rp03_issues_for_chapters

    ch = _ch(11, foreshadow="")
    ch.extra["promise_fulfilled"] = "坊市残图被截杀，叶焚立下复仇之约"
    issues = _rp03_issues_for_chapters(
        [ch],
        [("大比前坊市发现神火残图", 4)],
    )
    assert issues == []


def test_rp01_not_blocked_when_fulfilled_in_window():
    """整卷一次规划越过 deadline 时，窗口内已有兑现则不应 RP-01。"""
    from app.services.outline_linter.rules_promises import promise_fulfilled_in_window

    text = "大比前坊市发现神火残图"
    fulfilled = {11: "坊市残图被截杀，叶焚立下复仇之约"}
    # max_global=60 > deadline=11，但第11章已兑现
    assert promise_fulfilled_in_window(fulfilled, text, 10, 1)


def test_build_repair_seed():
    report = LinterReport(
        issues=[
            LinterIssue(
                rule_id="CH-04",
                severity="critical",
                scope="chapter",
                message="empty cost",
                field="extra.choice_cost",
                chapter_number_in_volume=3,
            ),
        ],
    )
    report.finalize_status()
    seed = build_repair_seed(report)
    assert seed["must_fix_chapter_numbers"] == [3]
    assert "3" in seed["issues_by_chapter"]


def test_apply_outline_patch_writes_choice_cost():
    from app.models import OutlineNode
    from app.routers.outline.helpers.revisions import _apply_outline_patch_to_node

    node = OutlineNode(
        title="第7章：试炼",
        summary="核心事件",
        hook="开篇",
        node_type="chapter_plan",
        extra={"choice_cost": ""},
    )
    record = _apply_outline_patch_to_node(node, {
        "chapter_number": 7,
        "fields": {
            "choice_cost": "为救同门，主角暴露了隐藏血脉，被执法队盯上",
            "opening_hook": "执法队的灵识扫过藏身处，主角屏息",
        },
        "reason": "补写选择代价供下章承接",
    })
    assert "choice_cost" in record["fields_changed"]
    assert node.extra["choice_cost"].startswith("为救同门")
    assert node.hook.startswith("执法队")


def test_build_linter_fix_prompt_includes_neighbor_context():
    from app.services.outline_linter.linter_fix_service import build_linter_fix_prompt

    chapters = {
        6: {
            "number": 6,
            "title": "前章",
            "opening_hook": "…",
            "core_event": "…",
            "character_change": "",
            "protagonist_choice": "硬闯",
            "choice_cost": "身份暴露",
            "end_hook": "追兵已至",
        },
        7: {
            "number": 7,
            "title": "问题章",
            "opening_hook": "",
            "core_event": "试炼",
            "character_change": "",
            "protagonist_choice": "接受挑战",
            "choice_cost": "",
            "end_hook": "",
        },
    }
    system, prompt = build_linter_fix_prompt(
        project_title="测试书",
        genre="玄幻",
        selected_pairs=[(0, {
            "rule_id": "CH-04",
            "severity": "critical",
            "message": "第7章选择代价为空",
            "suggestion": "补写代价",
            "chapter_number_in_volume": 7,
        })],
        chapters_by_number=chapters,
    )
    assert "总编辑" in system or "大纲" in system
    assert "CH-04" in prompt
    assert "身份暴露" in prompt
    assert "choice_cost" in prompt


def test_cm_skips_heat_outside_current_volume():
    """未展开卷上的 heat 章不在本卷 CM-02 中报错。"""
    from app.services.outline_linter.rules_mysteries import lint_core_mysteries

    chapters = [_ch(i) for i in range(1, 31)]
    chapters[2].extra["foreshadow_ops"] = [
        {"op": "lay", "name": "生母留下的血玉", "theme": "身世"},
    ]
    project_extra = {
        "core_mysteries": [{
            "name": "生母留下的血玉",
            "mystery_type": "identity",
            "lay_chapter": 3,
            "heat_chapters": [85, 160],
            "reveal_chapter": 255,
        }],
    }

    issues = lint_core_mysteries(
        None, "pid", chapters, volume_start_global=1, project_extra=project_extra,
    )
    assert not [i for i in issues if i.rule_id == "CM-02"]


def test_cm_flags_lay_missing_in_current_volume():
    from app.services.outline_linter.rules_mysteries import lint_core_mysteries

    chapters = [_ch(i) for i in range(1, 31)]
    project_extra = {
        "core_mysteries": [{
            "name": "被挖斗骨的诅咒",
            "mystery_type": "reversal",
            "lay_chapter": 6,
            "heat_chapters": [42],
            "reveal_chapter": 125,
        }],
    }

    issues = lint_core_mysteries(
        None, "pid", chapters, volume_start_global=1, project_extra=project_extra,
    )
    cm01 = [i for i in issues if i.rule_id == "CM-01"]
    cm02 = [i for i in issues if i.rule_id == "CM-02"]
    assert len(cm01) == 1
    assert "被挖斗骨的诅咒" in cm01[0].message
    assert len(cm02) == 0


def test_cm_skips_heat_outside_current_volume():
    """未展开卷上的 heat 章不在本卷 CM-02 中报错。"""
    from app.services.outline_linter.rules_mysteries import lint_core_mysteries

    chapters = [_ch(i) for i in range(1, 31)]
    chapters[2].extra["foreshadow_ops"] = [
        {"op": "lay", "name": "生母留下的血玉", "theme": "身世"},
    ]
    project_extra = {
        "core_mysteries": [{
            "name": "生母留下的血玉",
            "mystery_type": "identity",
            "lay_chapter": 3,
            "heat_chapters": [85, 160],
            "reveal_chapter": 255,
        }],
    }

    issues = lint_core_mysteries(
        None, "pid", chapters, volume_start_global=1, project_extra=project_extra,
    )
    assert not [i for i in issues if i.rule_id == "CM-02"]


def test_cm_flags_lay_missing_in_current_volume():
    from app.services.outline_linter.rules_mysteries import lint_core_mysteries

    chapters = [_ch(i) for i in range(1, 31)]
    project_extra = {
        "core_mysteries": [{
            "name": "被挖斗骨的诅咒",
            "mystery_type": "reversal",
            "lay_chapter": 6,
            "heat_chapters": [42],
            "reveal_chapter": 125,
        }],
    }

    issues = lint_core_mysteries(
        None, "pid", chapters, volume_start_global=1, project_extra=project_extra,
    )
    cm01 = [i for i in issues if i.rule_id == "CM-01"]
    cm02 = [i for i in issues if i.rule_id == "CM-02"]
    assert len(cm01) == 1
    assert "被挖斗骨的诅咒" in cm01[0].message
    assert len(cm02) == 0

