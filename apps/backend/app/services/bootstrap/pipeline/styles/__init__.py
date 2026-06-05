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
            "positioning_fanqie",       # Phase A: 算法立项
            "gate_positioning_fanqie",  # Phase A: 确认闸门
            "project_fanqie",           # Phase A: 项目创建
            "fanqie_formula",           # Phase B: 爽文公式（合并：落差+金手指+打脸地图）
            "power_ladder",             # Phase B: 权力阶梯
            "ctx_bridge",               # Phase B: 番茄ctx→通用ctx桥接
            "factions_fanqie",          # Phase C: 势力体系
            "storylines_fanqie",        # Phase C: 故事线
            "antagonist_ladder_fanqie", # Phase C: 卷级对立面
            "gate_characters",          # Phase C: 人物确认闸门
            "settings_fanqie",          # Phase C: 世界观设定（精简3张）
            "volumes_fanqie",           # Phase D: 卷级骨架
            "gate_volumes",             # Phase D: 卷质量闸门
            "rhythm_map_fanqie",        # Phase E: 节奏图（规则+LLM备用弧）
            "promise_seeds_fanqie",     # Phase F: 谜题钩子+开局承诺（合并）
            "signal_audit",             # Phase G: 番茄算法双校验（含consistency）
        ],
        default_writing_style="plain",
        # opening_contract 已合并进 promise_seeds_fanqie，从 CORE_NODES 中排除
        # consistency 已由 signal_audit 内置处理，无需独立节点
        skip_core=frozenset({"opening_contract", "consistency"}),
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
            # consistency_scan 已移除，由 CORE_NODE "consistency" 自动注入
            "canon_audit",
        ],
        default_writing_style="plain",
    ),
}


def get_style(style_id: str) -> StyleConfig:
    if style_id not in STYLE_REGISTRY:
        raise KeyError(f"未知 Bootstrap 风格: {style_id}")
    return STYLE_REGISTRY[style_id]
