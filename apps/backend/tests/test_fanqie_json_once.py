"""番茄 Bootstrap 单轮 JSON 调用：失败即抛 FanqieStepError。"""
from __future__ import annotations

import pytest

from app.services.bootstrap.json_once import BootstrapStepError, call_bootstrap_json_once

# 兼容旧名
FanqieStepError = BootstrapStepError
call_fanqie_json_once = call_bootstrap_json_once


class _FakeSvc:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    async def _call_with_retry(self, system, prompt, *, max_tokens=None, task=None) -> str:
        return self._raw


@pytest.mark.asyncio
async def test_call_fanqie_json_once_parse_error():
    svc = _FakeSvc("not json")
    with pytest.raises(BootstrapStepError, match=r"JSON 解析失败"):
        await call_fanqie_json_once(
            svc,
            step="test_step",
            system="s",
            prompt="p",
            task="bootstrap.positioning",
            validate=lambda _: None,
        )


@pytest.mark.asyncio
async def test_call_fanqie_json_once_validation_error():
    svc = _FakeSvc('{"a": 1}')
    with pytest.raises(BootstrapStepError, match=r"缺少字段"):
        await call_fanqie_json_once(
            svc,
            step="test_step",
            system="s",
            prompt="p",
            task="bootstrap.positioning",
            validate=lambda d: "缺少字段：b" if "b" not in d else None,
        )


@pytest.mark.asyncio
async def test_call_fanqie_json_once_success():
    svc = _FakeSvc('{"genre_archetype": "系统升级流", "core_satisfaction": "打脸"}')
    out = await call_fanqie_json_once(
        svc,
        step="fanqie_positioning",
        system="s",
        prompt="p",
        task="bootstrap.positioning",
        validate=lambda d: None if d.get("genre_archetype") else "empty",
    )
    assert out["genre_archetype"] == "系统升级流"
