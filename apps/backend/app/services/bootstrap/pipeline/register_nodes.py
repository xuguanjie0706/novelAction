"""注册全部 Bootstrap 节点到 NODE_CATALOG（import 时执行一次）。"""
from __future__ import annotations

from app.services.bootstrap.pipeline.catalog import register_node
from app.services.bootstrap.pipeline.node_spec import NodeSpec, PromptHook
from app.services.bootstrap.prompts.volumes import build_fanfic_volumes_block

_FANFIC_VOL_HOOK = PromptHook("volumes", build_fanfic_volumes_block)


def _register_all() -> None:
    from app.services.bootstrap.graph import (
        node_antagonist_ladder,
        node_core_mysteries,
        node_factions,
        node_gate,
        node_opening_contract,
        node_positioning,
        node_power_systems,
        node_project,
        node_settings,
        node_storylines,
    )
    from app.services.bootstrap.graph_gates import (
        node_gate_characters,
        node_gate_power_systems,
        node_gate_volumes,
    )
    from app.services.bootstrap.graph_nodes import (
        node_characters,
        node_consistency,
        node_emotion_villain,
        node_memory_relations,
        node_skills_items,
        node_volumes,
    )

    # ── 通用 / CORE ─────────────────────────────────────────
    register_node(NodeSpec(
        key="positioning_general", fn=node_positioning, seq=100,
        graph_id="positioning", label="召开立项会议（题材定位）...",
        is_positioning=True,
    ))
    register_node(NodeSpec(
        key="gate_positioning", fn=node_gate, seq=150,
        graph_id="gate", interrupt_before=True,
    ))
    register_node(NodeSpec(key="project", fn=node_project, seq=200, label="生成项目基础信息..."))
    register_node(NodeSpec(key="power_systems", fn=node_power_systems, seq=400, label="生成境界体系..."))
    register_node(NodeSpec(key="gate_power_systems", fn=node_gate_power_systems, seq=499, graph_id="gate_power_systems"))
    register_node(NodeSpec(key="factions", fn=node_factions, seq=500, label="生成势力体系..."))
    register_node(NodeSpec(key="storylines", fn=node_storylines, seq=510, label="生成故事线..."))
    register_node(NodeSpec(key="antagonist_ladder", fn=node_antagonist_ladder, seq=520, label="规划卷级对立面阶梯..."))
    register_node(NodeSpec(key="characters", fn=node_characters, seq=600, label="生成人物库..."))
    register_node(NodeSpec(key="gate_characters", fn=node_gate_characters, seq=650, graph_id="gate_characters"))
    register_node(NodeSpec(key="skills_items", fn=node_skills_items, seq=700))
    register_node(NodeSpec(key="settings", fn=node_settings, seq=710, label="生成世界观设定卡..."))
    register_node(NodeSpec(key="volumes", fn=node_volumes, seq=800, label="规划卷级结构..."))
    register_node(NodeSpec(key="gate_volumes", fn=node_gate_volumes, seq=850, graph_id="gate_volumes"))
    register_node(NodeSpec(key="emotion_villain", fn=node_emotion_villain, seq=860))
    register_node(NodeSpec(key="memory_relations", fn=node_memory_relations, seq=900))
    register_node(NodeSpec(key="core_mysteries", fn=node_core_mysteries, seq=910, label="预分配全书核心谜题..."))
    register_node(NodeSpec(key="opening_contract", fn=node_opening_contract, seq=920, label="规划开局追读承诺..."))
    register_node(NodeSpec(key="consistency", fn=node_consistency, seq=940, label="全局一致性扫描..."))

    # ── 番茄线 ───────────────────────────────────────────────
    from app.services.bootstrap.graph_fanqie import (
        node_antagonist_ladder as fanqie_antagonist_ladder,
        node_audit as fanqie_audit,
        node_contrast,
        node_consistency_scan,
        node_ctx_bridge,
        node_face_slap as fanqie_face_slap,
        node_fanqie_gate,
        node_fanqie_positioning,
        node_factions as fanqie_factions,
        node_golden_finger as fanqie_golden_finger,
        node_opening_contract as fanqie_opening_contract,
        node_power_ladder,
        node_project as fanqie_project,
        node_core_mysteries as fanqie_core_mysteries,
        node_rhythm as fanqie_rhythm,
        node_settings as fanqie_settings,
        node_storylines as fanqie_storylines,
        node_volumes as fanqie_volumes,
    )

    register_node(NodeSpec(
        key="positioning_fanqie", fn=node_fanqie_positioning, seq=100,
        graph_id="positioning", is_positioning=True,
    ))
    register_node(NodeSpec(
        key="gate_positioning_fanqie", fn=node_fanqie_gate, seq=150,
        graph_id="gate", interrupt_before=True,
    ))
    register_node(NodeSpec(key="project_fanqie", fn=fanqie_project, seq=200, graph_id="project", replaces="project"))
    register_node(NodeSpec(key="contrast_design", fn=node_contrast, seq=301, label="设计主角落差（越惨越爽）..."))
    register_node(NodeSpec(
        key="golden_finger_fanqie", fn=fanqie_golden_finger, seq=302,
        graph_id="golden_finger", label="设计金手指工程...",
    ))
    register_node(NodeSpec(
        key="face_slap_map_fanqie", fn=fanqie_face_slap, seq=303,
        graph_id="face_slap_map", label="规划打脸地图...",
    ))
    register_node(NodeSpec(
        key="power_ladder", fn=node_power_ladder, seq=304,
        label="构建权力阶梯（最小化世界观）...", replaces="power_systems",
    ))
    register_node(NodeSpec(key="ctx_bridge", fn=node_ctx_bridge, seq=305))
    register_node(NodeSpec(
        key="factions_fanqie", fn=fanqie_factions, seq=500,
        graph_id="factions", replaces="factions",
    ))
    register_node(NodeSpec(
        key="storylines_fanqie", fn=fanqie_storylines, seq=510,
        graph_id="storylines", replaces="storylines",
    ))
    register_node(NodeSpec(
        key="antagonist_ladder_fanqie", fn=fanqie_antagonist_ladder, seq=520,
        graph_id="antagonist_ladder", replaces="antagonist_ladder",
    ))
    register_node(NodeSpec(
        key="settings_fanqie", fn=fanqie_settings, seq=710,
        graph_id="settings", replaces="settings",
    ))
    register_node(NodeSpec(
        key="volumes_fanqie", fn=fanqie_volumes, seq=800,
        graph_id="volumes", replaces="volumes",
    ))
    register_node(NodeSpec(
        key="rhythm_map_fanqie", fn=fanqie_rhythm, seq=870,
        graph_id="rhythm_map", label="生成爽点节奏图 + 剧情储量池...",
    ))
    register_node(NodeSpec(
        key="core_mysteries_fanqie", fn=fanqie_core_mysteries, seq=910,
        graph_id="core_mysteries", replaces="core_mysteries",
    ))
    register_node(NodeSpec(
        key="opening_contract_fanqie", fn=fanqie_opening_contract, seq=920,
        graph_id="opening_contract", replaces="opening_contract",
    ))
    register_node(NodeSpec(
        key="consistency_scan", fn=node_consistency_scan, seq=935,
        graph_id="consistency", replaces="consistency",
    ))
    register_node(NodeSpec(key="signal_audit", fn=fanqie_audit, seq=950, label="执行番茄算法双校验..."))

    # ── 同人线 ───────────────────────────────────────────────
    from app.services.bootstrap.graph_fanfic import (
        node_audit as fanfic_audit,
        node_canon_characters,
        node_canon_pack,
        node_canon_power,
        node_deviation,
        node_entry_hook,
        node_face_slap as fanfic_face_slap,
        node_fanfic_gate,
        node_fanfic_positioning,
        node_golden_finger as fanfic_golden_finger,
        node_project as fanfic_project,
        node_rhythm as fanfic_rhythm,
        node_volumes as fanfic_volumes,
    )

    register_node(NodeSpec(
        key="positioning_fanfic", fn=node_fanfic_positioning, seq=100,
        graph_id="positioning", is_positioning=True,
    ))
    register_node(NodeSpec(
        key="gate_positioning_fanfic", fn=node_fanfic_gate, seq=150,
        graph_id="gate", interrupt_before=True,
    ))
    register_node(NodeSpec(key="project_fanfic", fn=fanfic_project, seq=200, graph_id="project", replaces="project"))
    register_node(NodeSpec(
        key="canon_pack", fn=node_canon_pack, seq=311,
        label="结构化原著设定...", prompt_hooks=[_FANFIC_VOL_HOOK],
    ))
    register_node(NodeSpec(key="deviation_contract", fn=node_deviation, seq=312, label="订立魔改边界..."))
    register_node(NodeSpec(key="entry_hook", fn=node_entry_hook, seq=313, label="设计穿书/重生/AU 切入点..."))
    register_node(NodeSpec(
        key="golden_finger_fanfic", fn=fanfic_golden_finger, seq=314,
        graph_id="golden_finger", label="设计同人金手指/信息差...",
    ))
    register_node(NodeSpec(
        key="face_slap_map_fanfic", fn=fanfic_face_slap, seq=315,
        graph_id="face_slap_map", label="规划打脸地图...",
    ))
    register_node(NodeSpec(
        key="canon_power", fn=node_canon_power, seq=316,
        label="提炼原著权力阶梯...", replaces="power_systems",
    ))
    register_node(NodeSpec(
        key="canon_characters", fn=node_canon_characters, seq=530,
        label="原著人物建档...", replaces="characters",
    ))
    register_node(NodeSpec(
        key="volumes_fanfic", fn=fanfic_volumes, seq=800,
        graph_id="volumes", replaces="volumes",
    ))
    register_node(NodeSpec(
        key="rhythm_map_fanfic", fn=fanfic_rhythm, seq=870,
        graph_id="rhythm_map", label="生成爽点节奏图...",
    ))
    register_node(NodeSpec(key="canon_audit", fn=fanfic_audit, seq=960, label="原著贴合 + 爽感双校验..."))


_register_all()
