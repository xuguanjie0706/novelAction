"""Bootstrap checkpoint 恢复辅助模块。

进程重启后 MemorySaver 清空，此模块负责从 DB 重建 Bootstrap ctx，
使 resume 在任意 gate 节点暂停后都能正确继续后续步骤。

从 graph.py 分离的原因：_rebuild_ctx_from_db 代码量大且职责独立，
提取后可保持 graph.py < 600 行（架构红线）。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def rebuild_ctx_from_db(
    db,
    project_id: str,
    gd: dict,
    logline: str,
    premise: str,
    target_words: int,
) -> dict:
    """根据已落库数据重建 Bootstrap ctx，供进程重启后 resume 使用。

    重建逻辑按 gate 类型分层：
    - gate_power_systems 暂停：需要 positioning + power_systems 数据
    - gate_characters    暂停：还需要 char_names / char_profiles 等
    - gate_volumes       暂停：还需要 _volume_ids / chapter_quota 等

    Args:
        db: 数据库会话。
        project_id: 项目 ID（字符串）。
        gd: BootstrapRun.gate_data 字典。
        logline: 小说创意一句话。
        premise: 作者补充说明。
        target_words: 全书目标字数。

    Returns:
        尽量完整的 ctx 字典，缺失字段保持默认值，不会引发 KeyError。
    """
    from app.models import Character, OutlineNode, PowerSystem, Project
    from app.services.bootstrap.power_registry import merge_power_into_ctx
    from app.services.outline_planning import words_to_plan

    positioning = gd.get("positioning") or {}
    ctx: dict = {
        "logline": logline,
        "premise": premise,
        "target_words": target_words,
        "positioning": positioning,
    }

    if not project_id:
        return ctx

    # ── 境界体系（Step 2 产物）────────────────────────────────────────────────
    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project_id)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    if pss:
        proj = db.query(Project).filter(Project.id == project_id).first()
        merge_power_into_ctx(ctx, pss, project=proj)

    # ── 人物库（Step 5 产物）──────────────────────────────────────────────────
    chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .order_by(Character.created_at)
        .all()
    )
    if chars:
        ctx["char_names"] = [c.name for c in chars]
        ctx["protagonist"] = next(
            (c.name for c in chars if c.role == "protagonist"), chars[0].name
        )
        ctx["char_realms"] = {c.name: (c.current_realm or "未知") for c in chars}
        ctx["char_name_to_id"] = {c.name: str(c.id) for c in chars}
        ctx["_char_ids"] = [str(c.id) for c in chars]
        ctx["core_char_names"] = [
            c.name for c in chars if c.character_tier in ("core", "arc")
        ]
        ctx["char_profiles"] = {
            c.name: {
                "core_wound": (c.fear or "").strip(),
                "current_desire": (c.motivation or "").strip(),
                "biggest_lie": "",
                "relationship_pressure": "",
                "values": (c.values or "").strip(),
                "arc": (c.arc or "").strip(),
            }
            for c in chars
            if c.role == "protagonist" or c.character_tier in ("core", "arc")
        }
        ctx["plot_npc_summary"] = "; ".join(
            f"{c.name}（{(c.extra or {}).get('vol1_function', '')}）"
            for c in chars
            if c.character_tier == "plot" and (c.extra or {}).get("vol1_function")
        )

    # ── 卷骨架（Step 9 产物）──────────────────────────────────────────────────
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if volumes:
        ctx["_volume_ids"] = [str(v.id) for v in volumes]
        ctx["volumes_summary"] = " | ".join(
            f"{v.title}：{(v.summary or '')[:40]}" for v in volumes
        )
        plan = words_to_plan(target_words)
        ctx["chapter_quota_total"] = plan["total_chapters"]
        ctx["chapter_quota_total_volumes"] = plan["total_volumes"]
        ctx["chapter_quota_used"] = 0  # 恢复时保守重置，续跑时会重新累积

    return ctx
