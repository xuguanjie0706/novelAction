"""
ingredient_prompt.py — 投料清单格式化为 prompt 注入文本

将 ChapterIngredients 格式化为可注入分场/起草 prompt 的约束文本块。
供 scene_routes.py 的 scene_plan_save 和 scene_draft_stream 使用。
"""
from __future__ import annotations

from app.services.ai.ingredient_types import ChapterIngredients


def build_constraints_prompt_block(ingredients: ChapterIngredients) -> str:
    """
    将 ChapterIngredients 格式化为可注入分场/起草 prompt 的约束文本块。

    供 scene_routes.py 的 scene_plan_save 和 scene_draft_stream 使用。
    """
    parts: list[str] = []

    # 故事线推进任务
    must_moves = [m for m in ingredients.storyline_moves if m.must_advance]
    optional_moves = [m for m in ingredients.storyline_moves if not m.must_advance]
    if must_moves or optional_moves:
        lines = []
        for m in must_moves:
            beat = f"→ 建议节拍：{m.suggested_beat}" if m.suggested_beat else ""
            lines.append(
                f"  [MUST] 「{m.name}」（{m.line_type}）"
                f"已断档 {m.gap_chapters} 章，本章必须推进。{beat}"
            )
        for m in optional_moves[:2]:
            lines.append(f"  [可选] 「{m.name}」（{m.line_type}）")
        parts.append("【故事线推进任务】\n" + "\n".join(lines))

    # 债务偿还
    critical_debts = [d for d in ingredients.debt_flags if d.severity == "critical"]
    warn_debts = [d for d in ingredients.debt_flags if d.severity == "warning"]
    if critical_debts or warn_debts:
        lines = []
        for d in critical_debts:
            lines.append(f"  🔴 [MUST] {d.description}")
        for d in warn_debts:
            lines.append(f"  🟡 [警告] {d.description}")
        parts.append("【本章必须偿还的债务】\n" + "\n".join(lines))

    # 伏笔操作
    if ingredients.foreshadow_ops:
        lines = []
        for op in ingredients.foreshadow_ops:
            overdue_tag = "【逾期】" if op.is_overdue else ""
            lines.append(
                f"  {op.op.upper()} {overdue_tag}「{op.title}」：{op.suggested_method}"
            )
        parts.append("【伏笔操作】\n" + "\n".join(lines))

    # 势力地盘着色
    if ingredients.faction_colors:
        lines = []
        for fc in ingredients.faction_colors:
            lines.append(
                f"  「{fc.name}」（{fc.faction_type}/{fc.alignment}）"
                f"氛围：{fc.atmosphere[:60]}；NPC 态度：{fc.npc_default_attitude}"
            )
        parts.append("【势力/地盘着色】\n" + "\n".join(lines))

    # 技能/法宝聚光灯
    if ingredients.asset_spotlight:
        lines = []
        for a in ingredients.asset_spotlight:
            effect = a.key_effect[:60] if a.key_effect else a.description[:60]
            lines.append(f"  【{a.name}】{effect}")
        parts.append("【本章技能/法宝聚光灯】\n" + "\n".join(lines))

    # 人物关系快照
    if ingredients.relationship_snapshots:
        lines = []
        for snap in ingredients.relationship_snapshots[:3]:
            lines.append(
                f"  {snap.char_a_name} ↔ {snap.char_b_name}："
                f"{snap.relation_type}（{snap.dynamic}）{snap.evolution_note[:60]}"
            )
        parts.append("【在场角色关系快照】\n" + "\n".join(lines))

    # 反派幕后动态
    if ingredients.villain_offscreen:
        parts.append(f"【反派幕后动态】\n  {ingredients.villain_offscreen[:200]}")

    # 情绪预算
    if ingredients.emotional_quota:
        quota = ingredients.emotional_quota
        tone = quota.get("volume_tone") or quota.get("primary_tone") or ""
        forbidden = quota.get("forbidden_tone") or ""
        if tone or forbidden:
            lines = []
            if tone:
                lines.append(f"  卷级基调：{tone}")
            if forbidden:
                lines.append(f"  禁止情绪：{forbidden}")
            parts.append("【情绪预算】\n" + "\n".join(lines))

    if not parts:
        return ""

    return (
        "\n\n===【本章投料约束（由系统主动计算，分场时必须分配落实）】===\n"
        + "\n\n".join(parts)
        + "\n===【约束结束】==="
    )
