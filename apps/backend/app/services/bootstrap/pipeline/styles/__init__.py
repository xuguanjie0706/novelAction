"""STYLE_REGISTRY — Bootstrap 风格注册表。"""
from __future__ import annotations

from app.services.bootstrap.pipeline.node_spec import StyleConfig

STYLE_REGISTRY: dict[str, StyleConfig] = {

    "sequential": StyleConfig(
        style_id="sequential",
        display_name="通用",
        nodes=[
            "positioning_general",
            "gate_positioning",
            "power_systems",
            "gate_power_systems",
            "gate_characters",
            "gate_volumes",
        ],
        default_writing_style="standard",
    ),

    "fanqie": StyleConfig(
        style_id="fanqie",
        display_name="番茄",
        nodes=[
            "positioning_fanqie",
            "gate_positioning_fanqie",
            "project_fanqie",
            "contrast_design",
            "golden_finger_fanqie",
            "face_slap_map_fanqie",
            "power_ladder",
            "ctx_bridge",
            "factions_fanqie",
            "storylines_fanqie",
            "antagonist_ladder_fanqie",
            "gate_characters",
            "settings_fanqie",
            "volumes_fanqie",
            "gate_volumes",
            "rhythm_map_fanqie",
            "core_mysteries_fanqie",
            "opening_contract_fanqie",
            "consistency_scan",
            "signal_audit",
        ],
        default_writing_style="plain",
    ),

    "fanfic": StyleConfig(
        style_id="fanfic",
        display_name="同人",
        nodes=[
            "positioning_fanfic",
            "gate_positioning_fanfic",
            "project_fanfic",
            "canon_pack",
            "deviation_contract",
            "entry_hook",
            "golden_finger_fanfic",
            "face_slap_map_fanfic",
            "canon_power",
            "canon_characters",
            "gate_characters",
            "gate_volumes",
            "volumes_fanfic",
            "rhythm_map_fanfic",
            "consistency_scan",
            "canon_audit",
        ],
        default_writing_style="plain",
    ),
}


def get_style(style_id: str) -> StyleConfig:
    if style_id not in STYLE_REGISTRY:
        raise KeyError(f"未知 Bootstrap 风格: {style_id}")
    return STYLE_REGISTRY[style_id]
