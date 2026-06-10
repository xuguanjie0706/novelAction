"""dabai 正文 prompt 与章纲解析测试。"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.dabai.draft_prompt import (
    build_dabai_chapter_elements_block,
    build_dabai_draft_prompt,
)
from app.services.dabai.outline_plan import resolve_chapter_plan


def test_build_dabai_chapter_elements_block_includes_five_beats():
    plan = SimpleNamespace(
        extra={
            "realm_rank": 2,
            "location_name": "青云外门",
            "dabai": {
                "shuang_type": "群嘲反转",
                "yaqu_setup": "守门弟子百般刁难",
                "emotion_turn": "长老巡查路过",
                "yinbao": "劲风如刀扇飞百米",
                "shuang_payoff": "全场寂静，众弟子倒退",
                "witnesses": ["外门弟子", "林语嫣"],
            },
        },
        highlight="叶辰取回断剑，剑身共鸣",
        hook="叶辰取回断剑，剑身共鸣",
        expected_words=2000,
    )
    block = build_dabai_chapter_elements_block(plan)
    assert "憋屈" in block and "守门弟子百般刁难" in block
    assert "转折扳机" in block and "长老巡查路过" in block
    assert "引爆" in block and "劲风如刀" in block
    assert "爽点" in block and "全场寂静" in block
    assert "章末钩子" in block and "断剑" in block
    assert "见证者" in block and "林语嫣" in block


def test_build_dabai_draft_prompt_word_ceiling():
    project = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000001",
        title="万古第一神体",
        extra={
            "golden_finger": {"name": "吞噬系统", "core_ability": "吞噬升级"},
            "positioning": {"taboo_lines": ["现代科幻词"]},
        },
    )
    chapter = SimpleNamespace(title="第3章测试", sort_order=2)
    plan = SimpleNamespace(
        extra={"dabai": {"yaqu_setup": "被羞辱", "shuang_payoff": "当众打脸"}},
        highlight="更大风暴逼近",
        hook="更大风暴逼近",
        expected_words=2000,
    )
    system, user = build_dabai_draft_prompt(project, chapter, plan, replace_existing=True)
    assert "2200" in system or "2200" in user
    assert "章节要素" in user
    assert "被羞辱" in user
    assert "整章重写" in user


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeDB:
    def __init__(self, plan):
        self._plan = plan

    def query(self, model):
        return _FakeQuery(self._plan)


def test_resolve_chapter_plan_prefers_outline_node_id():
    plan_id = uuid4()
    plan = SimpleNamespace(id=plan_id, node_type="chapter_plan")
    chapter = SimpleNamespace(outline_node_id=plan_id, sort_order=5)
    db = _FakeDB(plan)
    got = resolve_chapter_plan(db, "proj", chapter)
    assert got is plan
