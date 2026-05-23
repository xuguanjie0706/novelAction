"""
scene_constraint_builder.py — 场景级约束文本构建器

职责：
  将已存储在 Scene 模型新字段中的约束数据（storyline_moves / faction_color /
  asset_spotlight / foreshadow_ops / debt_flags / relationship_snapshots）
  格式化为可直接注入逐场起草 prompt 的结构化文本块。

设计原则：
  - 场景起草时直接读 scene 自身约束字段，无需重新查询数据库
  - 关系快照从 OutlineNode.extra.pre_write_constraints 中按在场角色过滤
  - 输出控制在 800 字以内，避免撑爆 context 预算

调用方：
  scene_routes.py → scene_draft_stream 端点
  scene_draft.py  → SceneDraftMixin.scene_draft_stream
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def build_scene_constraint_block(
    scene,
    outline_node_extra: dict | None = None,
) -> str:
    """
    将 Scene 的约束字段格式化为起草 prompt 约束块。

    Args:
        scene: Scene ORM 对象（含 storyline_moves / faction_color /
               asset_spotlight / foreshadow_ops / debt_flags /
               structural_warnings 等字段）。
        outline_node_extra: OutlineNode.extra dict（可选），用于读取
                            pre_write_constraints.relationship_snapshots
                            并按 scene.characters_on_stage 过滤。

    Returns:
        格式化约束文本块；若无任何约束则返回空字符串。
    """
    parts: list[str] = []

    # ① 势力/地盘着色
    fc = scene.faction_color
    if fc and isinstance(fc, dict):
        parts.append(
            f"【地盘氛围】此地为「{fc.get('name', '?')}」势力管辖\n"
            f"  氛围：{fc.get('atmosphere', '')[:80]}\n"
            f"  NPC 默认态度：{fc.get('npc_default_attitude', '中立冷漠')}"
        )

    # ② 技能/法宝聚光灯
    spotlight = scene.asset_spotlight
    if spotlight and isinstance(spotlight, list):
        lines = []
        for a in spotlight[:4]:
            if not isinstance(a, dict):
                continue
            name = a.get("name", "?")
            effect = (a.get("key_effect") or a.get("description") or "")[:80]
            cost = a.get("cost_or_rarity") or ""
            cost_str = f"（{cost}）" if cost else ""
            lines.append(f"  ·【{name}】{cost_str}{effect}")
        if lines:
            parts.append("【本场可用技能/法宝】\n" + "\n".join(lines))

    # ③ 故事线推进指令
    moves = scene.storyline_moves
    if moves and isinstance(moves, list):
        lines = []
        for m in moves[:3]:
            if not isinstance(m, dict):
                continue
            must = m.get("must_advance", False)
            tag = "[MUST] " if must else "[可选] "
            name = m.get("name", "?")
            beat = m.get("suggested_beat", "") or ""
            beat_str = f" → {beat}" if beat else ""
            lines.append(f"  {tag}「{name}」{beat_str}")
        if lines:
            parts.append("【本场必须推进的故事线】\n" + "\n".join(lines))

    # ④ 伏笔操作指令
    fw_ops = scene.foreshadow_ops
    if fw_ops and isinstance(fw_ops, list):
        lines = []
        for op in fw_ops[:3]:
            if not isinstance(op, dict):
                continue
            op_name = op.get("op", "hint").upper()
            title = op.get("title", "?")
            method = (op.get("suggested_method") or "")[:60]
            overdue = "【逾期】" if op.get("is_overdue") else ""
            lines.append(f"  {op_name} {overdue}「{title}」：{method}")
        if lines:
            parts.append("【伏笔操作】\n" + "\n".join(lines))

    # ⑤ 债务标记（仅 critical）
    debts = scene.debt_flags
    if debts and isinstance(debts, list):
        critical = [d for d in debts if isinstance(d, dict) and d.get("severity") == "critical"]
        if critical:
            lines = [f"  🔴 {d.get('description', '')[:80]}" for d in critical[:2]]
            parts.append("【本场必须偿还的债务】\n" + "\n".join(lines))

    # ⑥ 人物关系快照（从 pre_write_constraints 过滤在场角色）
    rel_block = _build_relationship_block(scene, outline_node_extra)
    if rel_block:
        parts.append(rel_block)

    # ⑦ 结构预警（信息层，供 AI 参考但不强制）
    warns = scene.structural_warnings
    if warns and isinstance(warns, list):
        lines = [f"  ⚠ {w.get('msg', '')}" for w in warns[:2] if isinstance(w, dict)]
        if lines:
            parts.append("【结构预警（参考）】\n" + "\n".join(lines))

    if not parts:
        return ""

    return (
        "\n\n===【本场投料约束（写正文时必须体现）】===\n"
        + "\n\n".join(parts)
        + "\n===【约束结束】==="
    )


def _build_relationship_block(scene, outline_node_extra: dict | None) -> str:
    """
    从 outline_node_extra.pre_write_constraints.relationship_snapshots
    过滤出在场角色之间的关系快照，格式化为文本块。
    """
    if not outline_node_extra:
        return ""

    constraints = outline_node_extra.get("pre_write_constraints") or {}
    snapshots = constraints.get("relationship_snapshots") or []
    if not snapshots:
        return ""

    on_stage = set(str(cid) for cid in (scene.characters_on_stage or []))
    if len(on_stage) < 2:
        return ""

    lines = []
    for snap in snapshots:
        if not isinstance(snap, dict):
            continue
        a_id = str(snap.get("char_a_id", ""))
        b_id = str(snap.get("char_b_id", ""))
        if a_id not in on_stage and b_id not in on_stage:
            continue
        a_name = snap.get("char_a_name", "?")
        b_name = snap.get("char_b_name", "?")
        rel_type = snap.get("relation_type", "未知")
        dynamic = snap.get("dynamic", "stable")
        note = (snap.get("evolution_note") or "")[:80]
        dynamic_desc = {
            "stable": "稳定",
            "evolving": "发展中",
            "deteriorating": "恶化中",
            "broken": "破裂",
        }.get(dynamic, dynamic)
        lines.append(
            f"  {a_name} ↔ {b_name}：{rel_type}（{dynamic_desc}）{note}"
        )
        if len(lines) >= 3:
            break

    if not lines:
        return ""
    return "【在场角色关系快照】\n" + "\n".join(lines)
