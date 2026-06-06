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

    "xianxia": StyleConfig(
        style_id="xianxia",
        display_name="玄幻修仙直白（原生）",
        # 从零原生拓扑：题材语义层全部修仙原生，中立持久化步骤复用通用线（非番茄）。
        # 最终图中零番茄节点。canonical-first，无需 converge：cultivation 已 sync PowerSystem，
        # volumes_xianxia 已落卷级 rank，opening_contract/consistency 用通用 CORE 节点收尾。
        nodes=[
            "positioning_xianxia",       # A 立项：修仙第一性原理（数值爬升引擎，非打脸）
            "gate_positioning_xianxia",  # A 立项确认闸门
            # project：通用 CORE（读 ctx.positioning，中立）
            "cultivation_contract",      # B 境界主轴 + 境界预算契约（replaces power_systems）
            "golden_finger_xianxia",     # B 金手指（咬合境界轴）
            # factions / storylines / antagonist_ladder：通用 CORE（吃修仙 ctx）
            "gate_characters",           # C 人物确认闸门
            "settings_xianxia",          # C 修仙世界设定卡（replaces settings）
            "volumes_xianxia",           # D 契约执行式卷骨架（replaces volumes）
            "gate_volumes",              # D 卷质量闸门
            # E emotion_villain / memory_relations / core_mysteries / opening_contract：通用 CORE
            # G consistency：通用 CORE（emit complete 收尾）
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
