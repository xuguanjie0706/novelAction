"""跨章写章桥接与叙事认知台账单测。"""

import pytest
from types import SimpleNamespace

from app.services.ai.draft_continuity_bridge import detect_hook_rewind_risk
from app.services.ai.narrative_knowledge import (
    build_knowledge_boundary_lines,
    collect_golden_finger_terms,
    merge_narrative_knowledge_from_debrief,
    terms_hidden_from_narration,
)


def test_detect_hook_rewind_when_prev_already_awakened():
    prev_beats = ["林渊觉醒吞天神体，黑火涌出大堂"]
    prev_tail = "…而是我林渊，休了你！黑火如潮水涌出。"
    warn = detect_hook_rewind_risk(
        prev_beats,
        prev_tail,
        "黑火灼烧经脉的剧痛",
        "黑火灼烧经脉的剧痛，他狂笑不止",
    )
    assert warn is not None
    assert "重播" in warn or "倒带" in warn or "下一拍" in warn


def test_detect_hook_rewind_skips_unrelated_hook():
    warn = detect_hook_rewind_risk(
        ["纳兰拓拔剑"],
        "剑尖直指林渊咽喉。",
        "剑尖停住",
        "演武场钟声响起",
    )
    assert warn is None


def test_narrative_knowledge_hides_golden_finger_until_debrief():
    project = SimpleNamespace(
        extra={
            "golden_finger": {"finger_name": "吞天神体·九幽狻猊火"},
            "narrative_knowledge": {"public_terms": [], "protagonist_terms": []},
        }
    )
    hidden = terms_hidden_from_narration(project)
    assert any("吞天" in t for t in hidden)
    lines = build_knowledge_boundary_lines(project)
    assert any("禁止直呼" in ln for ln in lines)


def test_merge_narrative_knowledge_from_debrief():
    project = SimpleNamespace(
        extra={"golden_finger": {"finger_name": "吞天神体"}}
    )
    changed = merge_narrative_knowledge_from_debrief(
        project,
        chapter_number=2,
        in_world_named_terms=[],
        protagonist_known_terms=["吞天神体"],
        core_events=["写下休书甩脸"],
    )
    assert changed is True
    assert "吞天神体" in project.extra["narrative_knowledge"]["protagonist_terms"]
    assert not terms_hidden_from_narration(project) or "吞天神体" not in terms_hidden_from_narration(
        project
    )


def test_collect_golden_finger_terms_splits_compound_name():
    project = SimpleNamespace(
        extra={"golden_finger": {"finger_name": "吞天神体·九幽狻猊火"}}
    )
    terms = collect_golden_finger_terms(project)
    assert "吞天神体·九幽狻猊火" in terms
    assert "吞天神体" in terms


@pytest.mark.asyncio
async def test_draft_prompt_includes_bridge_context():
    captured = {}

    async def fake_stream(system: str, prompt: str, max_tokens: int = 4096, context=None, **kwargs):
        captured["prompt"] = prompt
        yield "正文"

    from app.services.ai_service import AIService

    svc = AIService()
    svc._stream_ai = fake_stream

    async for _ in svc.draft_assist_stream(
        chapter_title="第2章",
        outline_hook="黑火灼烧经脉",
        outline_summary="写休书",
        outline_conflict="",
        outline_highlight="",
        outline_foreshadow="",
        prev_chapter_tail="而是我林渊，休了你！黑火涌出。",
        world_summary="",
        character_summary="林渊",
        memory_summary="",
        existing_content="",
        draft_bridge_context="▍上章已发生（时间线已锁定，禁止倒带重播）",
    ):
        pass

    assert "禁止倒带" in captured["prompt"] or "上章已发生" in captured["prompt"]
