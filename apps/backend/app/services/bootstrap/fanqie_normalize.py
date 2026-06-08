"""
番茄 Bootstrap 产物 → 标准 OutlineNode / PowerSystem 归一化。

原则：Diverge upstream, converge downstream。
规划层保留 Project.extra['fanqie_*']；章纲/卷骨架/境界表写入与通用线相同的列与 extra 契约。
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models import OutlineNode, PowerSystem, Project

OPENING_EXPECTED_WORDS = 2100
_SUMMARY_MAX = 600
_TEXT_MAX = 500


def infer_chapter_title(ch_num: int, ch: dict) -> str:
    """无 title 时从核心事件截取短标题。"""
    title = (ch.get("title") or "").strip()
    if title:
        return title[:300]
    for key in (
        "core_event",
        "first_slap_scene",
        "escalation",
        "commitment_hook",
        "small_win",
    ):
        text = (ch.get(key) or "").strip()
        if text:
            short = text.replace("\n", " ")[:14]
            return short + ("…" if len(text) > 14 else "")
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    for key in ("act_1_setup", "opening_200_words", "act_3_finger"):
        text = (struct.get(key) or "").strip()
        if text:
            short = text.replace("\n", " ")[:14]
            return short + ("…" if len(text) > 14 else "")
    return f"第{ch_num}章"


def build_chapter_summary(ch: dict) -> str:
    """标准 summary：优先 core_event，第一章用 structure 拼接。"""
    core = (ch.get("core_event") or "").strip()
    if core:
        return core[:_SUMMARY_MAX]
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    if struct:
        parts = [
            (struct.get("act_1_setup") or "").strip(),
            (struct.get("act_2_trigger") or "").strip(),
            (struct.get("act_3_finger") or "").strip(),
        ]
        joined = " ".join(p for p in parts if p)
        if joined:
            return joined[:_SUMMARY_MAX]
    for key in ("first_slap_scene", "escalation", "small_win"):
        text = (ch.get(key) or "").strip()
        if text:
            return text[:_SUMMARY_MAX]
    return ""


def build_chapter_conflict(ch: dict) -> str | None:
    """障碍/冲突 → conflict 列（编剧台读 conflict / extra.obstacle）。"""
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    obstacle = (
        (struct.get("act_1_setup") or "").strip()
        or (ch.get("escalation") or "").strip()
        or (struct.get("opening_200_words") or "").strip()
    )
    return obstacle[:_TEXT_MAX] if obstacle else None


def build_chapter_hook(ch: dict, ch_num: int) -> str | None:
    """章末钩子 → hook 列。"""
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    hook = (ch.get("ending_hook") or struct.get("ending_hook") or "").strip()
    if ch_num == 5:
        commit = (ch.get("commitment_hook") or "").strip()
        if commit and hook:
            return f"{hook}（{commit}）"[:_TEXT_MAX]
        return (commit or hook)[:_TEXT_MAX] or None
    return hook[:_TEXT_MAX] if hook else None


def build_power_milestone(ch: dict, ch_num: int, first_slap_ch: int) -> str | None:
    slap = (ch.get("first_slap_scene") or "").strip()
    if slap:
        return slap[:_TEXT_MAX]
    if ch_num == first_slap_ch:
        return slap[:_TEXT_MAX] if slap else None
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    finger = (struct.get("act_3_finger") or "").strip()
    return finger[:_TEXT_MAX] if finger and ch_num == 1 else None


def pacing_from_rhythm_tag(tag_type: str | None) -> str | None:
    if not tag_type:
        return None
    return {
        "big_win": "climax",
        "small_win": "fast",
        "progress": "normal",
        "transition": "slow",
    }.get(str(tag_type), "normal")


def build_chapter_extra(
    ch: dict,
    ch_num: int,
    *,
    first_slap_ch: int = 3,
) -> dict:
    """与 steps/chapter_extra.build_chapter_extra 对齐的番茄开局 extra。"""
    summary = build_chapter_summary(ch)
    obstacle = build_chapter_conflict(ch) or ""
    struct = ch.get("structure") if isinstance(ch.get("structure"), dict) else {}
    ending = (ch.get("ending_hook") or struct.get("ending_hook") or "").strip()
    extra: dict[str, Any] = {
        "fanqie_chapter": ch,
        "completion_rate_target": ch.get("completion_rate_target"),
        "ending_hook": ending,
        "end_hook": ending,
        "chapter_end_hook": ending,
        "bootstrap_generated": True,
        "bootstrap_fanqie": True,
        "lazy_expanded": False,
    }
    if summary:
        extra["core_event"] = summary[:300]
    if obstacle:
        extra["protagonist_obstacle"] = obstacle[:300]
        extra["obstacle"] = obstacle[:300]
    if ch_num == first_slap_ch or (ch.get("first_slap_scene") or "").strip():
        extra["has_face_slap"] = True
    small = (ch.get("small_win") or "").strip()
    peak = (ch.get("emotion_peak") or "").strip()
    if peak:
        extra["reader_emotion_target"] = peak[:200]
    elif small:
        extra["reader_emotion_target"] = small[:200]
    esc = (ch.get("escalation") or "").strip()
    if esc:
        extra["villain_action"] = esc[:200]
    return extra


def apply_normalized_chapter_plan(
    node: OutlineNode,
    ch_num: int,
    ch: dict,
    *,
    first_slap_ch: int = 3,
) -> None:
    """将番茄开局章数据写入标准 OutlineNode 列 + extra。"""
    if not ch:
        return
    node.title = infer_chapter_title(ch_num, ch)
    node.summary = build_chapter_summary(ch) or node.summary
    node.conflict = build_chapter_conflict(ch)
    hook = build_chapter_hook(ch, ch_num)
    node.hook = hook
    node.highlight = hook
    node.power_milestone = build_power_milestone(ch, ch_num, first_slap_ch)
    tone = (ch.get("emotion_peak") or ch.get("small_win") or "").strip()
    node.emotional_tone = tone[:50] if tone else node.emotional_tone
    node.phase = node.phase or "opening"
    node.expected_words = OPENING_EXPECTED_WORDS
    target = ch.get("completion_rate_target")
    if isinstance(target, (int, float)) and target > 0:
        node.reader_hook_score = min(10, max(1, int(round(float(target) / 10))))
    node.extra = {
        **(node.extra or {}),
        **build_chapter_extra(ch, ch_num, first_slap_ch=first_slap_ch),
    }
    flag_modified(node, "extra")


def _parse_chapter_hint(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    m = re.search(r"\d+", str(raw))
    return int(m.group()) if m else None


def normalize_opening_volume(
    vol: OutlineNode,
    project: Project,
    ctx: dict | None = None,
) -> None:
    """开局卷写入导演单 extra（planned_chapters / beat_highlights 等）。"""
    ctx = ctx or {}
    proj_extra = project.extra or {}
    fanqie_pos = ctx.get("fanqie_positioning") or proj_extra.get("positioning") or {}
    fsm = ctx.get("face_slap_map") or proj_extra.get("face_slap_map") or {}
    rhythm = ctx.get("rhythm_map") or proj_extra.get("rhythm_map") or {}
    ladder = ctx.get("power_ladder") or proj_extra.get("power_ladder") or {}

    if not (vol.summary or "").strip():
        vol.summary = (
            (fanqie_pos.get("core_satisfaction") or fanqie_pos.get("selling_point") or "")
            .strip()[:_TEXT_MAX]
            or None
        )

    extra = dict(vol.extra or {})
    tags = rhythm.get("chapter_tags") if isinstance(rhythm, dict) else []
    existing_planned = extra.get("planned_chapters")
    if isinstance(existing_planned, int) and 15 <= existing_planned <= 80:
        planned = existing_planned
    else:
        planned = 50
        if isinstance(tags, list) and tags:
            ch_nums = [
                int(t["ch"]) for t in tags
                if isinstance(t, dict) and t.get("ch") is not None
            ]
            if ch_nums:
                planned = max(planned, max(ch_nums))
    extra["planned_chapters"] = planned

    beats: list[dict] = list(extra.get("beat_highlights") or [])
    if not beats and isinstance(fsm.get("targets"), list):
        for t in fsm["targets"][:6]:
            if not isinstance(t, dict):
                continue
            hint = _parse_chapter_hint(t.get("chapter_estimate")) or t.get("order")
            desc = (t.get("slap_scene") or t.get("name") or "").strip()
            if desc:
                beats.append({
                    "chapter_hint": hint or 1,
                    "beat_type": "face_slap",
                    "description": desc[:200],
                })
    if beats:
        extra["beat_highlights"] = beats

    preview = (fsm.get("first_slap_preview") or "").strip()
    slap_ch = int(fsm.get("first_slap_chapter") or 3)
    if preview:
        extra["volume_climax"] = {
            "chapter_hint": slap_ch,
            "description": preview[:300],
        }
        if not (vol.highlight or "").strip():
            vol.highlight = preview[:_TEXT_MAX]

    if isinstance(tags, list) and tags:
        from app.services.bootstrap.rhythm_pacing import refresh_opening_volume_pacing_skeleton

        planned_ch = extra.get("planned_chapters") or planned
        skeleton = refresh_opening_volume_pacing_skeleton(
            extra.get("pacing_skeleton") or "",
            tags,
            preview_chapters=int(planned_ch) if planned_ch else planned,
        )
        if skeleton:
            extra["pacing_skeleton"] = skeleton

    social = ladder.get("social_ladder") if isinstance(ladder, dict) else []
    if isinstance(social, list) and social:
        start_t = social[0] if isinstance(social[0], dict) else {}
        end_t = social[-1] if isinstance(social[-1], dict) else {}
        if start_t.get("name"):
            extra["protagonist_realm_start"] = str(start_t["name"])
        if end_t.get("name"):
            extra["protagonist_realm_end"] = str(end_t["name"])

    extra["fanqie_opening_volume"] = True
    vol.extra = extra
    vol.phase = vol.phase or "opening"
    flag_modified(vol, "extra")


def apply_rhythm_tags_to_opening_chapters(
    db: Session,
    project: Project,
    rhythm_map: dict,
    *,
    max_chapter: int = 5,
) -> int:
    """用 rhythm_map 前 N 章标签 patch 已有开局 chapter_plan.pacing。"""
    tags = rhythm_map.get("chapter_tags") if isinstance(rhythm_map, dict) else []
    if not isinstance(tags, list):
        return 0
    by_ch = {
        int(t["ch"]): t
        for t in tags
        if isinstance(t, dict) and t.get("ch") is not None
    }
    vol = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .first()
    )
    if not vol:
        return 0
    nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.parent_id == vol.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    patched = 0
    for node in nodes:
        ch_num = chapter_index_from_node(node)
        if ch_num > max_chapter:
            continue
        tag = by_ch.get(ch_num)
        if not tag:
            continue
        pacing = pacing_from_rhythm_tag(tag.get("type"))
        if pacing:
            node.pacing = pacing
        ex = dict(node.extra or {})
        ex["rhythm_tag"] = tag.get("type")
        note = (tag.get("note") or "").strip()
        if note:
            ex["rhythm_note"] = note[:200]
        if tag.get("type") in ("big_win", "small_win"):
            ex["has_face_slap"] = tag.get("type") == "big_win" or bool(ex.get("has_face_slap"))
        node.extra = ex
        flag_modified(node, "extra")
        patched += 1
    return patched


def sync_power_ladder_to_power_system(db: Session, project: Project) -> PowerSystem | None:
    """power_ladder → 一条 PowerSystem（纪要/世界观页读标准表）。"""
    ladder = (project.extra or {}).get("power_ladder")
    if not isinstance(ladder, dict) or not ladder.get("social_ladder"):
        return None

    existing = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project.id)
        .order_by(PowerSystem.sort_order)
        .first()
    )
    levels = []
    for item in ladder.get("social_ladder") or []:
        if not isinstance(item, dict):
            continue
        levels.append({
            "rank": item.get("tier") or len(levels) + 1,
            "name": (item.get("name") or "").strip() or f"第{len(levels) + 1}阶",
            "description": (item.get("description") or "").strip(),
            "representative": (item.get("representative") or "").strip(),
        })
    if not levels:
        return existing

    axis_kind = (ladder.get("axis_kind") or "social").strip() or "social"
    realm_axis_name = (ladder.get("realm_axis_name") or "").strip()
    ps_name = (
        realm_axis_name[:48]
        if axis_kind == "cultivation" and realm_axis_name
        else f"{(project.title or '本书')[:24]}·修炼阶梯"
    )
    breakthrough = (
        (ladder.get("breakthrough_signature") or "").strip()
        if axis_kind == "cultivation"
        else ""
    ) or (ladder.get("power_visualization") or "").strip() or None
    payload = {
        "name": ps_name,
        "system_type": "cultivation",
        "description": (ladder.get("world_core_rule") or "").strip(),
        "levels": levels,
        "protagonist_current_rank": ladder.get("protagonist_start_tier") or 1,
        "protagonist_end_rank": ladder.get("protagonist_end_tier") or len(levels),
        "breakthrough_condition": breakthrough,
        "special_rules": (ladder.get("wealth_visualization") or "").strip() or None,
        "extra": {
            "source": "fanqie_power_ladder",
            "axis_kind": axis_kind,
            "sub_realm_segments": ladder.get("sub_realm_segments")
            or ["初期", "中期", "后期", "圆满"],
            "realm_axis_name": realm_axis_name or None,
        },
    }

    if existing:
        for key, val in payload.items():
            if key == "extra":
                merged = dict(existing.extra or {})
                merged.update(val)
                existing.extra = merged
            else:
                setattr(existing, key, val)
        flag_modified(existing, "extra")
        db.commit()
        return existing

    ps = PowerSystem(project_id=project.id, sort_order=0, **payload)
    db.add(ps)
    db.commit()
    db.refresh(ps)
    return ps


def distribute_volume_realm_ranks(start: int, end: int, n: int) -> list[tuple[int, int]]:
    """把全书主角境界 [start, end] 单调分摊到 n 卷，返回每卷 (start_rank, end_rank)。

    纯函数（便于回归测试）：卷末 rank 线性插值后取整、非递减；卷首接上一卷卷末。
    """
    if n <= 0:
        return []
    if end < start:
        end = start
    out: list[tuple[int, int]] = []
    prev_end = start
    for i in range(n):
        vol_start = start if i == 0 else prev_end
        vol_end = round(start + (end - start) * (i + 1) / n)
        vol_end = max(vol_start, min(vol_end, end))
        out.append((vol_start, vol_end))
        prev_end = vol_end
    return out


def backfill_fanqie_volume_realm_ranks(db: Session, project: Project) -> int:
    """回填番茄/同人卷节点的 protagonist_realm_start_rank/end_rank（方向1 让插值轴生效）。

    番茄/同人线的 gen_volumes 早于 PowerSystem 生成，卷节点缺主角境界 rank，导致章级境界轴
    （realm_axis）失效。converge 时 PowerSystem 已建好，据其主角起止 rank 把全书境界单调分摊到各卷，
    使每章（含未写突破点的）都能插值出应有境界。幂等：已有 rank 的卷不覆盖。
    """
    from app.routers.outline.helpers.realm_timeline import _realm_display_name_for_rank
    from app.routers.outline.helpers.realm_whitelist import build_realm_rank_map

    systems = db.query(PowerSystem).filter(PowerSystem.project_id == project.id).all()
    if not systems:
        return 0
    name_to_rank, _max, _ = build_realm_rank_map(systems)
    if not name_to_rank:
        return 0
    rank_values = sorted(set(name_to_rank.values()))
    min_rank, top_rank = rank_values[0], rank_values[-1]

    primary = min(systems, key=lambda s: s.sort_order or 0)
    start = getattr(primary, "protagonist_current_rank", None)
    end = getattr(primary, "protagonist_end_rank", None)
    start = start if isinstance(start, int) and start > 0 else min_rank
    end = end if isinstance(end, int) and end > 0 else top_rank
    start = max(min_rank, min(start, top_rank))
    end = max(start, min(end, top_rank))

    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project.id, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if not volumes:
        return 0

    dist = distribute_volume_realm_ranks(start, end, len(volumes))
    updated = 0
    for vol, (vs, ve) in zip(volumes, dist):
        ex = dict(vol.extra or {})
        sr = ex.get("protagonist_realm_start_rank")
        er = ex.get("protagonist_realm_end_rank")
        if (
            isinstance(sr, int)
            and isinstance(er, int)
            and sr > 0
            and er > 0
        ):
            continue  # 幂等：已有有效 rank（如通用线已填）不覆盖；rank≤0 视为历史脏数据须修复
        ex["protagonist_realm_start_rank"] = vs
        ex["protagonist_realm_end_rank"] = ve
        sname = _realm_display_name_for_rank(vs, name_to_rank)
        ename = _realm_display_name_for_rank(ve, name_to_rank)
        if sname:
            ex.setdefault("protagonist_realm_start", sname)
        if ename:
            ex.setdefault("protagonist_realm_end", ename)
        vol.extra = ex
        flag_modified(vol, "extra")
        updated += 1
    if updated:
        db.commit()
    return updated


def is_fanqie_project(project: Project, ctx: dict | None = None) -> bool:
    """番茄项目：pace_type=fast 或 extra 含 fanqie_positioning（兼容旧 opening_5chapters）。"""
    ctx = ctx or {}
    pos = ctx.get("positioning") or (project.extra or {}).get("positioning") or {}
    if pos.get("pace_type") == "fast":
        return True
    extra = project.extra or {}
    if extra.get("fanqie_positioning"):
        return True
    return bool(extra.get("opening_5chapters"))


def ensure_fanqie_opening_volume(
    db: Session,
    project: Project,
    ctx: dict | None = None,
) -> OutlineNode:
    """Bootstrap：仅创建/更新第一卷卷纲（导演单 extra），不创建 chapter_plan。"""
    ctx = ctx or {}
    vol = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .first()
    )
    if not vol:
        vol = OutlineNode(
            project_id=project.id,
            node_type="volume",
            title="第一卷",
            sort_order=0,
            phase="opening",
        )
        db.add(vol)
        db.flush()
    normalize_opening_volume(vol, project, ctx)
    db.commit()
    return vol


def upsert_opening_chapter_plans(
    db: Session,
    project: Project,
    opening_data: dict,
    ctx: dict | None = None,
) -> None:
    """创建或更新第一卷下开局 1–5 章 chapter_plan（标准列 + extra）。"""
    ctx = ctx or {}
    fsm = ctx.get("face_slap_map") or (project.extra or {}).get("face_slap_map") or {}
    first_slap = int(fsm.get("first_slap_chapter") or 3)

    vol = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .first()
    )
    if not vol:
        vol = OutlineNode(
            project_id=project.id,
            node_type="volume",
            title="第一卷",
            sort_order=1,
            phase="opening",
        )
        db.add(vol)
        db.flush()

    normalize_opening_volume(vol, project, ctx)

    existing = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.parent_id == vol.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    by_order = {chapter_index_from_node(n): n for n in existing}

    for ch_num in range(1, 6):
        ch = opening_data.get(f"chapter_{ch_num}") or {}
        if not isinstance(ch, dict) or not ch:
            continue
        node = by_order.get(ch_num)
        if node is None:
            node = OutlineNode(
                project_id=project.id,
                parent_id=vol.id,
                node_type="chapter_plan",
                sort_order=ch_num - 1,
                phase="opening",
            )
            db.add(node)
        apply_normalized_chapter_plan(node, ch_num, ch, first_slap_ch=first_slap)

    db.commit()


def converge_fanqie_project(db: Session, project: Project, ctx: dict | None = None) -> None:
    """
    Bootstrap 番茄流程收敛：卷导演单 + 境界表；不物化 chapter_plan。
  """
    ctx = ctx or {}
    vol = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .first()
    )
    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    vol = volumes[0] if volumes else None
    if vol:
        normalize_opening_volume(vol, project, ctx)
        db.commit()

    from app.services.bootstrap.volume_chapter_starts import reconcile_volume_planned_from_starts

    if reconcile_volume_planned_from_starts(volumes):
        db.commit()

    sync_power_ladder_to_power_system(db, project)

    # 方向1：PowerSystem 已建好，回填卷级主角境界 rank，使章级境界轴对番茄/同人线生效。
    backfill_fanqie_volume_realm_ranks(db, project)

    # 开局承诺回填：番茄线不跑通用 Step 12，从 rhythm_map/face_slap_map 派生 opening_contract
    # + ReaderPromise，补上番茄追读命脉，让 UI 与下游章纲/复盘复用既有契约。
    from app.services.bootstrap.fanqie_opening_contract import (
        backfill_fanqie_opening_contract,
    )

    backfill_fanqie_opening_contract(db, project)


def backfill_fanqie_project(
    db: Session,
    project_id: str,
    *,
    strip_chapter_plans: bool = False,
) -> None:
    """存量番茄项目：卷纲/境界表归一化；可选清除已物化章纲以便重新按需展开。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"project not found: {project_id}")
    if strip_chapter_plans:
        from app.services.bootstrap.fanqie_volume_expand import strip_volume_chapter_plans

        strip_volume_chapter_plans(db, project)
    converge_fanqie_project(db, project, ctx=dict(project.extra or {}))
