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

    # 番茄（fanqie）线已下线：从 STYLE_REGISTRY / mode 枚举 / 前端选项移除，
    # graph_fanqie.py 等文件保留为废弃存根（同人/修仙线仍复用其中的纯工具函数）。
    # 取而代之的是「斗破·大白文玄幻」线，见下方 "doupo"。

    "doupo": StyleConfig(
        style_id="doupo",
        display_name="斗破·大白文玄幻",
        # 完全基于通用（sequential）线：复用通用 project / storylines / characters /
        # skills_items / volumes / memory / mysteries / opening_contract / consistency，
        # 仅替换三处题材语义节点 + 合并势力/对立面，并对共享 volumes 挂大纲质量增强 hook。零番茄耦合。
        nodes=[
            "positioning_doupo",          # Step0 斗气大陆纯爽文立项（禁修仙/禁上帝视角）
            "gate_positioning_doupo",     # Step0 确认闸门
            "power_axis_doupo",           # Step2 单斗气主轴（replaces 修仙多轴 power_systems）
            "gate_power_systems",         # Step2 斗气主轴确认闸门
            "factions_antagonist_doupo",  # Step3+4.5 势力+卷级对立面 一次LLM（replaces factions，吞 antagonist_ladder）
            "gate_characters",            # 人物确认闸门（功法/法宝在其后由 CORE skills_items 生成，精确挂 UUID）
            "settings_doupo",             # Step8 精简斗气大陆世界卡（replaces settings，6张）
            "gate_volumes",               # 卷质量闸门
        ],
        default_writing_style="plain",
        # antagonist_ladder 已并入 factions_antagonist_doupo，从 CORE_NODES 中排除；
        # skills_items 保留为 CORE（人物后生成，精确挂 UUID）。
        skip_core=frozenset({"antagonist_ladder"}),
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
            "factions_antagonist_xianxia",  # C 势力+卷级对立面合并（replaces factions，吞 antagonist_ladder，-1 LLM）
            # storylines：通用 CORE（吃修仙 ctx）
            "gate_characters",           # C 人物确认闸门
            "settings_xianxia",          # C 修仙世界设定卡（replaces settings）
            "volumes_xianxia",           # D 契约执行式卷骨架（replaces volumes）
            "gate_volumes",              # D 卷质量闸门
            # E emotion_villain / memory_relations：通用 CORE
            "promise_seeds_xianxia",     # F 核心谜题+开局承诺合并（replaces core_mysteries，吞 opening_contract，-1 LLM）
            # G consistency：通用 CORE（emit complete 收尾）
        ],
        default_writing_style="plain",
        # antagonist_ladder / opening_contract 已被两个合并节点吞并，排除其独立 CORE 节点
        skip_core=frozenset({"antagonist_ladder", "opening_contract"}),
    ),

    "dabai": StyleConfig(
        style_id="dabai",
        display_name="大白文·修仙",
        # 约 5 次 LLM：立项 / 金手指+境界 / 势力+人物+故事线 / 功法+道具 / 卷+地图；章纲写作期懒展开。
        nodes=[
            "positioning_dabai",
            "gate_positioning_dabai",
            "golden_power_dabai",
            "cast_world_dabai",
            "volumes_map_dabai",
            "gate_volumes",
            "dabai_bootstrap_lint",
        ],
        default_writing_style="plain",
        skip_core=frozenset({
            "power_systems", "gate_power_systems",
            "factions", "storylines", "antagonist_ladder", "characters", "gate_characters",
            "settings", "volumes", "emotion_villain", "memory_relations",
            "core_mysteries", "opening_contract", "consistency",
        }),
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
