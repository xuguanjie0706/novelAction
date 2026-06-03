"""按卷展开章纲时的番茄增强上下文块。

当 pace_type == "fast" 时，从 Project.extra 读取番茄 Bootstrap 增强产物
（contrast_design / golden_finger / face_slap_map / rhythm_map / signal_audit），
组装为注入 prompt 的结构化约束块。

这些产物由 graph_fanqie_enhance.py 的增强节点在标准管线中生成。
"""
from __future__ import annotations

from app.models import OutlineNode, Project
from app.services.bootstrap.chapter_plan_batches import normalize_volume_planned_chapters


def _volume_planned_chapters(volume_node: OutlineNode) -> int:
    """与 vol_chapter_plans / routes_vol_expand 一致：读卷 extra.planned_chapters。"""
    return normalize_volume_planned_chapters((volume_node.extra or {}).get("planned_chapters"))


def build_fanqie_enhance_block(
    project: Project,
    volume_node: OutlineNode,
    ctx: dict,
) -> str:
    """组装番茄增强上下文块，注入章纲生成 prompt。

    Args:
        project:     当前项目（读 extra 字段）。
        volume_node: 目标卷。
        ctx:         当前上下文 dict（可选附加信息）。

    Returns:
        番茄增强 prompt 块字符串；无增强产物时返回空串。
    """
    extra = project.extra if isinstance(project.extra, dict) else {}
    parts: list[str] = []

    # ── 落差工程 ──────────────────────────────────────────────────────────
    contrast = extra.get("contrast_design")
    if isinstance(contrast, dict) and contrast:
        parts.append(
            "\n【番茄落差工程（主角初始耻辱 → 终态逆袭，开局节奏硬约束）】\n"
            f"  初始状态：{contrast.get('initial_state_headline', '（未设定）')}\n"
            f"  触发事件：{contrast.get('trigger_event', '（未设定）')}\n"
            f"  触发位置：{contrast.get('trigger_word_estimate', '约800字')}\n"
            f"  终态成就：{contrast.get('final_destination', '（未设定）')}\n"
            f"  落差说明：{contrast.get('contrast_ratio_note', '')}\n"
            "  ⚠️ 开局前5章必须体现从「初始耻辱」到「金手指初显威力」的落差弧线。"
        )

    # ── 金手指工程 ─────────────────────────────────────────────────────────
    gf = extra.get("golden_finger")
    if isinstance(gf, dict) and gf:
        stages = gf.get("upgrade_stages") or []
        stage_lines = []
        for s in stages[:5]:
            if isinstance(s, dict):
                stage_lines.append(
                    f"    阶段{s.get('stage', '?')} {s.get('name', '')}："
                    f"解锁{s.get('unlock_ability', '')}，"
                    f"打脸{s.get('face_slap_target', '')}，"
                    f"约{s.get('chapter_range', '?')}章"
                )
        parts.append(
            "\n【番茄金手指工程（爽感引擎 + 成长路线图）】\n"
            f"  名称：{gf.get('finger_name', '')}（{gf.get('finger_type', '')}）\n"
            f"  核心机制：{(gf.get('mechanism') or '')[:120]}\n"
            f"  可视化方式：{gf.get('visualization_style', '')}\n"
            f"  限制/代价：{gf.get('constraint', '')}\n"
            f"  升级路线图：\n" + "\n".join(stage_lines) + "\n"
            "  ⚠️ 章纲中每次金手指升级必须对应 power_milestone，"
            "且升级画面必须用 visualization_style 描述的方式呈现。"
        )

    # ── 打脸地图 ──────────────────────────────────────────────────────────
    fsm = extra.get("face_slap_map")
    if isinstance(fsm, dict) and fsm:
        targets = fsm.get("targets") or []
        target_lines = []
        for t in targets[:5]:
            if isinstance(t, dict):
                target_lines.append(
                    f"    Lv{t.get('order', '?')} {t.get('name', '')}（{t.get('relation', '')}）"
                    f"→ {t.get('slap_type', '')}，约第{t.get('chapter_estimate', '?')}章"
                )
        parts.append(
            "\n【番茄打脸地图（对象谱系 + 升级路径，章纲 has_face_slap 硬约束）】\n"
            f"  打脸节奏：{fsm.get('slap_rhythm', '每3章一小打，每10章一大打')}\n"
            f"  升级路径：{fsm.get('escalation_path', '')}\n"
            f"  首次打脸：第{fsm.get('first_slap_chapter', '?')}章 — "
            f"{fsm.get('first_slap_preview', '')}\n"
            f"  打脸对象层级（从弱到强）：\n" + "\n".join(target_lines) + "\n"
            f"  类型多样性：{', '.join(fsm.get('type_diversity_plan') or [])}\n"
            "  ⚠️ has_face_slap=true 的章节必须指明打脸对象（从上方层级选），"
            "且打脸类型不能连续3次相同。"
        )

    # ── 爽点节奏图（前50章标签 + 干旱警告）────────────────────────────────
    rm = extra.get("rhythm_map")
    if isinstance(rm, dict) and rm:
        vol_sort = volume_node.sort_order or 0
        # 计算本卷在全书中的大致章号范围
        vol_start_ch = _estimate_volume_start_chapter(project, vol_sort)
        tags = rm.get("chapter_tags") or []
        relevant_tags = [
            t for t in tags
            if isinstance(t, dict) and isinstance(t.get("ch"), int)
        ]
        # 只展示与本卷相关的标签（±10章缓冲）
        planned = _volume_planned_chapters(volume_node)
        vol_end_ch = vol_start_ch + planned
        vol_tags = [
            t for t in relevant_tags
            if vol_start_ch - 5 <= t["ch"] <= vol_end_ch + 5
        ]
        if vol_tags:
            tag_lines = "  ".join(
                f"Ch{t['ch']}:{t.get('type', '?')}" for t in vol_tags[:20]
            )
        else:
            tag_lines = "（本卷范围无预设标签）"

        dry_spells = rm.get("auto_dry_spells") or rm.get("dry_spell_warnings") or []
        dry_warn = ""
        if dry_spells:
            dry_warn = f"\n  ⚠️ 干旱警告：{'; '.join(str(d) for d in dry_spells[:3])}"

        payoffs = rm.get("major_payoff_chapters") or []
        vol_payoffs = [ch for ch in payoffs if vol_start_ch <= ch <= vol_end_ch]

        parts.append(
            "\n【番茄爽点节奏图（本卷参考标签 + 干旱预警）】\n"
            f"  本卷对应全书章号范围：约第{vol_start_ch}-{vol_end_ch}章\n"
            f"  节奏标签：{tag_lines}\n"
            + (f"  本卷大爽点章节：{vol_payoffs}\n" if vol_payoffs else "")
            + dry_warn + "\n"
            "  标签类型说明：big_win=大爽点 | small_win=小爽点 | progress=推进 | transition=过渡\n"
            "  ⚠️ 连续2章 transition 必须插入至少1个 small_win；连续3章无 big_win/small_win 视为节奏断裂。"
        )

    # ── 算法双校验结果（如有）─────────────────────────────────────────────
    audit = extra.get("signal_audit")
    if isinstance(audit, dict) and audit:
        score = audit.get("overall_score", "?")
        passed = audit.get("overall_pass", True)
        fixes = audit.get("critical_fixes") or []
        tips = audit.get("algo_optimization_tips") or []
        if not passed or fixes:
            fix_lines = "\n".join(f"    - {f}" for f in fixes[:3])
            tip_lines = "\n".join(f"    - {t}" for t in tips[:2])
            parts.append(
                f"\n【番茄算法审计结果（总分{score}，{'通过' if passed else '未通过'}）】\n"
                f"  关键修复项：\n{fix_lines}\n"
                + (f"  优化建议：\n{tip_lines}\n" if tip_lines else "")
                + "  ⚠️ 章纲生成必须回应上述修复项，不能无视审计结论。"
            )

    if not parts:
        return ""
    return "\n".join(parts)


def _estimate_volume_start_chapter(project: Project, vol_sort_order: int) -> int:
    """估算指定卷在全书中的起始章号（累加前序卷的 planned_chapters）。"""
    if vol_sort_order <= 0:
        return 1
    from sqlalchemy.orm import object_session
    db = object_session(project)
    if not db:
        return vol_sort_order * 30 + 1  # 粗估

    prev_volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
            OutlineNode.sort_order < vol_sort_order,
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    total = sum(_volume_planned_chapters(v) for v in prev_volumes)
    return total + 1
