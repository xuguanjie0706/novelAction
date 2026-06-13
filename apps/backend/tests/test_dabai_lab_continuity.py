"""dabai 实验书架衔接增强：境界锁定 / 位移质检 / 分场承接。"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.dabai.lab_chapter_gate import dabai_chapter_generate_block_reason
from app.services.dabai.lab_quality import _check_location_bridge
from app.services.dabai.lab_prompt_shared import (
    build_location_bridge_block,
    build_power_ladder_block,
    build_witness_lock_block,
    fix_realm_string,
    inject_prewarn_into_scene_plan,
    is_bridge_scene,
    merge_opening_directive,
    needs_location_bridge,
    opening_continues_prev_tail,
    sanitize_prewarn_result,
)


def _project(**kwargs):
    base = {
        "power_ladder": {
            "levels": [
                {"rank": 1, "name": "引灵境"},
                {"rank": 2, "name": "凝煞境"},
            ],
        },
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _chapter(**kwargs):
    base = {
        "chapter_number": 2,
        "title": "测试章",
        "content": "",
        "location": "杂役宿舍·地火房",
        "witnesses": ["王猛的狗腿子"],
        "involved_characters": ["王猛", "李夜"],
        "expected_words": 2000,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_power_ladder_block_forbids_foreign_realm():
    block = build_power_ladder_block(_project())
    assert "引灵境" in block
    assert "练气" in block


def test_witness_lock_block_lists_names():
    block = build_witness_lock_block(_chapter())
    assert "王猛的狗腿子" in block
    assert "李夜" in block


def test_fix_realm_string_replaces_lianqi():
    assert fix_realm_string("练气一层", _project()) == "引灵境·第1层"
    assert fix_realm_string("引灵境·第2层", _project()) == "引灵境·第2层"


def test_sanitize_prewarn_result():
    raw = {"fact_lock": {"realm": "练气一层", "location": "乱葬岗"}}
    out = sanitize_prewarn_result(raw, _project())
    assert "练气" not in out["fact_lock"]["realm"]
    assert "引灵境" in out["fact_lock"]["realm"]


def test_chapter_generate_gate_blocks_without_prev_content():
    ch = _chapter(chapter_number=3, content="")
    prev = _chapter(chapter_number=2, content="", title="上一章")
    db = SimpleNamespace()
    db.query = lambda *args, **kwargs: SimpleNamespace(
        filter=lambda *a, **k: SimpleNamespace(first=lambda: prev),
    )
    reason = dabai_chapter_generate_block_reason(db, "proj-id", ch)
    assert reason is not None
    assert "第2章" in reason


def test_chapter_generate_gate_allows_chapter_one():
    ch = _chapter(chapter_number=1, content="")
    db = SimpleNamespace()
    assert dabai_chapter_generate_block_reason(db, "proj-id", ch) is None


def test_chapter_generate_gate_allows_rewrite():
    ch = _chapter(chapter_number=5, content="已有正文")
    db = SimpleNamespace()
    assert dabai_chapter_generate_block_reason(db, "proj-id", ch) is None


def test_chapter_generate_gate_allows_when_prev_written():
    ch = _chapter(chapter_number=2, content="")
    prev = _chapter(chapter_number=1, content="第一章正文")
    db = SimpleNamespace()
    db.query = lambda *args, **kwargs: SimpleNamespace(
        filter=lambda *a, **k: SimpleNamespace(first=lambda: prev),
    )
    assert dabai_chapter_generate_block_reason(db, "proj-id", ch) is None


def test_location_bridge_detects_missing_transition():
    prev = _chapter(chapter_number=1, location="乱葬岗·毒尸坑")
    curr = _chapter(chapter_number=2, location="杂役宿舍·地火房")
    opening = "张三把尸体摔在李夜脚边，屋里一阵哄笑。"
    issue = _check_location_bridge(curr, prev, opening)
    assert issue is not None
    assert issue["rule_id"] == "DLB-03"


def test_location_bridge_allows_movement_verbs():
    prev = _chapter(chapter_number=1, location="乱葬岗·毒尸坑")
    curr = _chapter(chapter_number=2, location="杂役宿舍·地火房")
    opening = "李夜收起黑旗，趁夜色潜回杂役宿舍，刚踏进院门，一具腐尸就砸在脚边。"
    assert _check_location_bridge(curr, prev, opening) is None


def test_location_bridge_skips_when_prev_tail_already_at_cave():
    prev = _chapter(chapter_number=4, location="宗门偏殿·执事堂")
    curr = _chapter(chapter_number=5, location="阴煞洞·矿脉深处")
    prev_tail = "阴煞洞深处，李夜攥紧断裂枪头，一双血红色的眼睛在黑暗中缓缓睁开。"
    opening = "红眼睁开的刹那，李夜不仅没有后退，反而迎着尸臭撞了上去。"
    assert _check_location_bridge(curr, prev, opening, prev_tail=prev_tail) is None


def test_normalize_opening_prewarn_moves_conflict_to_setup():
    from app.services.dabai.lab_pre_warn import normalize_opening_prewarn

    raw = {
        "conflict_notes": ["章纲捡幡与台账封印冲突：改为拨浪鼓碎裂露出残幡"],
        "beat_execution": {"yaqu": "..."},
    }
    out = normalize_opening_prewarn(raw, opening_no_prior=True)
    assert out["conflict_notes"] == []
    assert "拨浪鼓" in out["setup_alignment"][0]


def test_normalize_opening_prewarn_keeps_conflict_when_not_opening():
    from app.services.dabai.lab_pre_warn import normalize_opening_prewarn

    raw = {"conflict_notes": ["位置与上章矛盾"]}
    out = normalize_opening_prewarn(raw, opening_no_prior=False)
    assert out["conflict_notes"] == ["位置与上章矛盾"]
    assert "setup_alignment" not in out


def test_inject_bridge_scene_when_directives_present():
    ch = _chapter()
    plan = {
        "opening_line": "腐尸砸脚",
        "scenes": [{"order": 1, "name": "宿舍刁难", "goal": "憋屈", "word_budget": 800}],
    }
    pre_warn = {
        "opening_directive": "收起黑旗潜回宿舍",
        "bridge_directives": ["交代从乱葬岗走回收尸堂杂役宿舍"],
        "fact_lock": {"location": "杂役宿舍"},
    }
    out = inject_prewarn_into_scene_plan(plan, pre_warn, ch)
    assert "收起黑旗" in out["opening_line"]
    assert len(out["scenes"]) >= 2
    assert is_bridge_scene(out["scenes"][0])


def test_inject_bridge_scene_when_location_gap_without_directives():
    prev = _chapter(chapter_number=1, location="宗门偏殿·执事堂")
    ch = _chapter(chapter_number=2, location="阴煞洞·矿脉深处")
    plan = {
        "opening_line": "矿洞里阴风阵阵",
        "scenes": [{"order": 1, "name": "矿洞遇险", "goal": "憋屈", "word_budget": 800}],
    }
    out = inject_prewarn_into_scene_plan(plan, None, ch, prev)
    assert len(out["scenes"]) >= 2
    assert is_bridge_scene(out["scenes"][0])


def test_inject_skips_bridge_when_prev_tail_already_at_cave():
    prev = _chapter(
        chapter_number=4,
        location="宗门偏殿·执事堂",
        content="…李夜已经踏入阴煞洞深处，握住了断裂枪头。",
    )
    ch = _chapter(chapter_number=5, location="阴煞洞·矿脉深处")
    plan = {
        "opening_line": "紧接红眼",
        "scenes": [{"order": 1, "name": "尸王苏醒", "goal": "憋屈", "word_budget": 800}],
    }
    prev_tail = "阴煞洞深处，一双血红色的眼睛缓缓睁开。"
    out = inject_prewarn_into_scene_plan(plan, None, ch, prev, prev_tail=prev_tail)
    assert len(out["scenes"]) == 1
    assert not is_bridge_scene(out["scenes"][0])


def test_inject_strips_stale_bridge_when_prev_tail_at_cave():
    prev = _chapter(chapter_number=4, location="宗门偏殿·执事堂")
    ch = _chapter(chapter_number=5, location="阴煞洞·矿脉深处")
    plan = {
        "opening_line": "紧接红眼",
        "scenes": [
            {
                "order": 1,
                "name": "位移承接",
                "goal": "位移/承接上章",
                "event": "从宗门偏殿离开，经合理路径抵达阴煞洞",
                "word_budget": 250,
            },
            {"order": 2, "name": "尸王苏醒", "goal": "憋屈", "word_budget": 800},
        ],
    }
    prev_tail = "阴煞洞深处，一双血红色的眼睛缓缓睁开。"
    out = inject_prewarn_into_scene_plan(plan, None, ch, prev, prev_tail=prev_tail)
    assert len(out["scenes"]) == 1
    assert out["scenes"][0]["name"] == "尸王苏醒"


def test_build_location_bridge_block():
    prev = _chapter(chapter_number=1, location="宗门偏殿·执事堂")
    ch = _chapter(chapter_number=2, location="阴煞洞·矿脉深处")
    block = build_location_bridge_block(prev, ch)
    assert "DLB-03" in block
    assert "宗门偏殿" in block
    assert "阴煞洞" in block


def test_build_location_bridge_skips_when_prev_tail_at_destination():
    prev = _chapter(chapter_number=4, location="宗门偏殿·执事堂")
    ch = _chapter(chapter_number=5, location="阴煞洞·矿脉深处")
    prev_tail = "阴煞洞深处，李夜攥紧断裂枪头，一双血红色的眼睛在黑暗中睁开。"
    assert needs_location_bridge(prev, ch, prev_tail) is False
    assert build_location_bridge_block(prev, ch, prev_tail) == ""


def test_ch6_opening_continues_cave_exit_confrontation():
    """第5章末在洞口对峙沈幽然 → 第6章开篇同瞬间，不应触发 DLB-03。"""
    prev = _chapter(chapter_number=5, location="阴煞洞·矿脉深处")
    curr = _chapter(chapter_number=6, location="阴尸宗·偏僻草棚")
    prev_tail = (
        "李夜大步踏出洞口，迎着那抹冷得刺骨的月光，走向了那道等候多时的清冷身影。"
    )
    opening = (
        "李夜刚踏出阴煞洞，沈幽然那道清冷如月的身影便封住了去路。"
        "她站在那里，像一柄出鞘的寒剑，指尖寒芒直逼李夜怀中的黑旗。"
    )
    assert opening_continues_prev_tail(prev_tail, opening) is True
    assert needs_location_bridge(prev, curr, prev_tail) is False
    assert _check_location_bridge(curr, prev, opening, prev_tail=prev_tail) is None


def test_merge_opening_directive():
    merged = merge_opening_directive("腐尸砸脚", "收起黑旗潜回宿舍")
    assert merged.startswith("收起黑旗潜回宿舍")
