"""Bootstrap PipelineBuilder 单元测试。"""
from __future__ import annotations

import pytest

from app.services.bootstrap.pipeline.builder import CORE_NODES, _resolve_active_keys
from app.services.bootstrap.pipeline.styles import STYLE_REGISTRY


def test_sequential_includes_core_and_gates():
    keys = _resolve_active_keys(STYLE_REGISTRY["sequential"])
    assert "positioning_general" in keys
    assert "gate_positioning" in keys
    assert "power_systems" in keys
    assert "project" in keys
    assert "consistency" in keys
    assert "fanqie_contrast" not in keys


def test_fanqie_skips_power_systems_and_uses_power_ladder():
    keys = _resolve_active_keys(STYLE_REGISTRY["fanqie"])
    assert "power_ladder" in keys
    assert "power_systems" not in keys
    assert "signal_audit" in keys
    assert "consistency" not in keys
    assert "opening_contract" not in keys
    assert "promise_seeds_fanqie" in keys
    assert "volumes_fanqie" in keys
    assert "volumes" not in keys


def test_core_nodes_frozenset():
    assert "project" in CORE_NODES
    assert "positioning_general" not in CORE_NODES
