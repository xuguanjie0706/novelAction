"""新 Bootstrap 步骤产物 → editorial_prompt_block 构建器。

将 emotion_arc / villain_arc / core_mysteries 三个新步骤的产物
从 Project.extra 读取并格式化为 prompt 注入块，
由 context_vol_expand.build_vol_expand_ctx 调用。

独立成文件的原因：context_vol_expand.py 已接近红线，
新步骤相关的块构建逻辑集中于此，便于后续单独迭代。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import OutlineNode, Project


def build_new_steps_blocks(
    project: "Project",
    volume_node: "OutlineNode",
    ctx: dict,
) -> tuple[str, str, str]:
    """读取新 Bootstrap 步骤的 Project.extra 产物，构建三个 prompt 块。

    Args:
        project:     当前项目（含 extra JSON 字段）。
        volume_node: 目标卷节点（用于确定 vol_index 和章号范围）。
        ctx:         待写入摘要字段的上下文字典（emotion_arc / villain_arc /
                     core_mysteries / core_mysteries_summary）。

    Returns:
        (emotion_arc_block, villain_arc_block, core_mysteries_block)
        各为可直接拼入 editorial_prompt_block 的字符串，无产物时为空字符串。
    """
    extra = project.extra if isinstance(project.extra, dict) else {}
    vol_idx = volume_node.sort_order or 0

    emotion_arc_block = _build_emotion_arc_block(extra, vol_idx, ctx)
    villain_arc_block = _build_villain_arc_block(extra, vol_idx, ctx)
    core_mysteries_block = _build_core_mysteries_block(extra, volume_node, ctx)

    return emotion_arc_block, villain_arc_block, core_mysteries_block


# ── 各块构建私有函数 ───────────────────────────────────────────────────────────

def _build_emotion_arc_block(extra: dict, vol_idx: int, ctx: dict) -> str:
    """全书情绪节律图块（Step 9.5 产物）。"""
    emotion_arc = extra.get("emotion_arc", [])
    if not emotion_arc or not isinstance(emotion_arc, list):
        return ""

    ctx["emotion_arc"] = emotion_arc
    current_arc = next((v for v in emotion_arc if v.get("vol_index") == vol_idx), None)
    arc_lines = []
    for v in emotion_arc:
        marker = "▶" if v.get("vol_index") == vol_idx else " "
        arc_lines.append(
            f"  {marker}{v.get('vol_title', '卷')}："
            f"主色调={v.get('dominant_emotion', '?')}，"
            f"净余额={v.get('net_balance', '?')}"
        )
    block = "\n【全书情绪节律图（当前卷用▶标注，不得打破全书情绪节奏）】\n" + "\n".join(arc_lines)
    if current_arc:
        block += (
            f"\n  本卷编辑批注：{current_arc.get('arc_note', '')}"
            f"\n  本卷情绪目标：存入「{current_arc.get('emotional_deposit', '')}」"
            f"，消耗「{current_arc.get('emotional_cost', '')}」"
        )
    return block


def _build_villain_arc_block(extra: dict, vol_idx: int, ctx: dict) -> str:
    """反派独立行动线块（Step 9.8 产物）。"""
    villain_arc = extra.get("villain_arc", [])
    if not villain_arc or not isinstance(villain_arc, list):
        return ""

    ctx["villain_arc"] = villain_arc
    arc_lines = []
    for v in villain_arc:
        marker = "▶" if v.get("vol_index") == vol_idx else " "
        arc_lines.append(
            f"  {marker}{v.get('vol_title', '卷')}【{v.get('villain_name', '?')}】："
            f"目标={v.get('vol_goal', '')[:25]}，结果={v.get('vol_result', '?')}"
        )
    block = "\n【反派独立行动线（总编辑预分配，当前卷用▶标注）】\n" + "\n".join(arc_lines)
    cur = next((v for v in villain_arc if v.get("vol_index") == vol_idx), None)
    if cur:
        block += (
            f"\n  本卷反派目标：{cur.get('vol_goal', '')}"
            f"\n  本卷关键决策：{cur.get('vol_key_choice', '')}"
            f"\n  本卷付出代价：{cur.get('vol_cost', '')}"
            f"\n  盲区布局：{cur.get('hidden_move', '')}"
        )
    return block


def _build_core_mysteries_block(
    extra: dict,
    volume_node: "OutlineNode",
    ctx: dict,
) -> str:
    """本卷需操作的核心谜题块（Step 11.5 产物）。"""
    mysteries = extra.get("core_mysteries", [])
    if not mysteries or not isinstance(mysteries, list):
        return ""

    ctx["core_mysteries"] = mysteries
    ctx["core_mysteries_summary"] = "、".join(
        f"{m.get('name', '?')}(埋{m.get('lay_chapter', '?')}→揭{m.get('reveal_chapter', '?')}章)"
        for m in mysteries[:6]
    )

    vol_idx = volume_node.sort_order or 0
    vol_planned = (volume_node.extra or {}).get("planned_chapters", 30)

    # 估算本卷在全书中的章号范围（仅用于过滤，精度够用）
    all_vol_extras = extra.get("volumes") or []
    chapters_before = sum(
        (v.get("extra") or {}).get("planned_chapters", 60)
        for v in all_vol_extras
        if isinstance(v, dict) and v.get("sort_order", 0) < vol_idx
    )
    vol_ch_start = chapters_before + 1
    vol_ch_end = chapters_before + vol_planned

    lines = []
    for m in mysteries:
        ops = []
        if vol_ch_start <= m.get("lay_chapter", 0) <= vol_ch_end:
            ops.append(f"埋（第{m['lay_chapter']}章·{m.get('lay_method', '')[:20]}）")
        heats = [h for h in (m.get("heat_chapters") or []) if vol_ch_start <= h <= vol_ch_end]
        if heats:
            ops.append(f"加热（第{'、'.join(str(h) for h in heats)}章）")
        if vol_ch_start <= m.get("reveal_chapter", 0) <= vol_ch_end:
            ops.append(f"揭晓（第{m['reveal_chapter']}章·{m.get('reveal_method', '')[:20]}）")
        if ops:
            lines.append(f"  ▶【{m.get('name', '?')}】{'；'.join(ops)}")

    if not lines:
        return ""
    return (
        "\n【本卷需操作的核心谜题（总编辑预分配，必须在对应章节执行）】\n"
        + "\n".join(lines)
    )
