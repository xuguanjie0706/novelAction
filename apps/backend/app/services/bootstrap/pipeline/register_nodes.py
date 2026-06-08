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

    # ── 斗破·大白文玄幻线（mode=doupo，基于通用线，零番茄耦合）────────────
    # 番茄（fanqie）线已下线：其节点不再注册，graph_fanqie.py 文件保留为废弃存根。
    # doupo 仅替换四处题材语义节点，其余复用上方通用 CORE。
    from app.services.bootstrap.graph_doupo import (
        node_doupo_factions_antagonist,
        node_doupo_gate,
        node_doupo_positioning,
        node_doupo_power_axis,
        node_doupo_world,
    )
    from app.services.bootstrap.prompts.doupo_prompts import build_doupo_volumes_block

    register_node(NodeSpec(
        key="positioning_doupo", fn=node_doupo_positioning, seq=100,
        graph_id="positioning", is_positioning=True,
        # 大纲质量增强：对共享 volumes 步骤挂斗破式 prompt hook（仅 doupo 图生效）
        prompt_hooks=[PromptHook("volumes", build_doupo_volumes_block)],
    ))
    register_node(NodeSpec(
        key="gate_positioning_doupo", fn=node_doupo_gate, seq=150,
        graph_id="gate", interrupt_before=True,
    ))
    register_node(NodeSpec(
        key="power_axis_doupo", fn=node_doupo_power_axis, seq=400,
        graph_id="power_systems", replaces="power_systems",
        label="构建斗气阶位主轴（斗者→斗帝）...",
    ))
    # 合并：势力 + 卷级对立面 一次 LLM（占 factions 槽，吞 antagonist_ladder）
    # 功法/法宝改由通用 CORE skills_items 在人物后生成（精确挂 UUID），故 skip_core 不再排除 skills_items
    register_node(NodeSpec(
        key="factions_antagonist_doupo", fn=node_doupo_factions_antagonist, seq=500,
        graph_id="factions", replaces="factions",
        label="生成势力 + 卷级对立面（合并·Boss挂靠真实势力）...",
    ))
    register_node(NodeSpec(
        key="settings_doupo", fn=node_doupo_world, seq=710,
        graph_id="settings", replaces="settings",
        label="生成斗气大陆世界设定卡（精简6张）...",
    ))

    # ── 玄幻修仙直白线（mode=xianxia，从零原生拓扑）──────────────
    # 题材语义层全部原生（立项/金手指/境界契约/世界/卷骨架），
    # 中立持久化步骤（project/factions/characters/storylines/memory/mysteries/
    # opening_contract/consistency）复用通用线（非番茄）；最终图中零番茄节点。
    from app.services.bootstrap.graph_xianxia import (
        node_cultivation_contract,
        node_factions_antagonist_xianxia,
        node_golden_finger_xianxia,
        node_promise_seeds_xianxia,
        node_volumes_xianxia,
        node_world_xianxia,
        node_xianxia_gate,
        node_xianxia_positioning,
    )

    register_node(NodeSpec(
        key="positioning_xianxia", fn=node_xianxia_positioning, seq=100,
        graph_id="positioning", is_positioning=True,
    ))
    register_node(NodeSpec(
        key="gate_positioning_xianxia", fn=node_xianxia_gate, seq=150,
        graph_id="gate", interrupt_before=True,
    ))
    register_node(NodeSpec(
        key="cultivation_contract", fn=node_cultivation_contract, seq=304,
        label="构建修仙境界主轴 + 境界预算契约...", replaces="power_systems",
    ))
    register_node(NodeSpec(
        key="golden_finger_xianxia", fn=node_golden_finger_xianxia, seq=306,
        label="设计修仙金手指（咬合境界轴）...",
    ))
    # 合并：factions + antagonist_ladder → 一次 LLM（-1 调用）。
    # replaces=factions 占其槽位；antagonist_ladder 由 StyleConfig.skip_core 排除。
    register_node(NodeSpec(
        key="factions_antagonist_xianxia", fn=node_factions_antagonist_xianxia, seq=500,
        graph_id="factions", replaces="factions",
        label="生成势力体系 + 卷级对立面（合并）...",
    ))
    # 合并：core_mysteries + opening_contract → 一次 LLM（-1 调用）。
    # replaces=core_mysteries 占其槽位；opening_contract 由 StyleConfig.skip_core 排除。
    register_node(NodeSpec(
        key="promise_seeds_xianxia", fn=node_promise_seeds_xianxia, seq=915,
        graph_id="promise_seeds", replaces="core_mysteries",
        label="预置核心谜题 + 开局追读承诺（合并）...",
    ))
    register_node(NodeSpec(
        key="settings_xianxia", fn=node_world_xianxia, seq=710,
        graph_id="settings", replaces="settings",
        label="生成修仙世界设定卡...",
    ))
    register_node(NodeSpec(
        key="volumes_xianxia", fn=node_volumes_xianxia, seq=800,
        graph_id="volumes", replaces="volumes",
        label="规划卷骨架（境界预算契约硬执行）...",
    ))

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
