"""Bootstrap：title_blurb 失败不阻断章纲。"""
from __future__ import annotations

import pytest

from dabai.config import DabaiConfig
from dabai.pipeline import aiter_bootstrap
from dabai.steps import DabaiStepError


@pytest.mark.asyncio
async def test_title_blurb_failure_still_runs_chapter_outlines(monkeypatch):
    cfg = DabaiConfig(logline="测试", stop_after="chapter_outlines", volume_chapters=2)

    async def fake_run_step(step, ctx, call, cfg):
        if step == "volumes":
            return [{"volume_number": 1, "planned_chapters": 2, "title": "卷一"}]
        if step == "title_blurb":
            raise DabaiStepError("mock title_blurb fail")
        return {}

    async def fake_batches(ctx, call, cfg, vol, *, use_expand_window=False):
        batch = [{"chapter_number": 1, "title": "章1"}, {"chapter_number": 2, "title": "章2"}]
        yield batch, 1, 2

    monkeypatch.setattr("dabai.steps.run_step", fake_run_step)
    monkeypatch.setattr("dabai.steps.aiter_chapter_batches", fake_batches)

    events = []
    async for ev in aiter_bootstrap(cfg, lambda *a, **k: None):
        events.append(ev)

    assert any(e.get("event") == "step_error" and e.get("step") == "title_blurb" for e in events)
    assert any(e.get("event") == "step_done" and e.get("step") == "chapter_outlines" for e in events)
    end = next(e for e in events if e.get("event") == "bootstrap_end")
    assert "title_blurb" in end.get("failed_steps", [])
    assert len(end.get("ctx", {}).get("chapter_outlines") or []) == 2
