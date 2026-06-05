"""
Bootstrap 单步独立重跑服务。

职责：
  1. build_full_ctx(db, project) — 从 DB 完整重建 ctx，供任意步骤独立重跑
  2. wipe_step(db, project_id, step) — 删除目标步骤的 DB 产物（幂等）
  3. dispatch_regen(svc, project, step, ctx) — 分发到对应 gen_* 函数

调用方约定（路由层）：
  await dispatch_regen(svc, project, step, ctx)

代码红线：本文件 < 250 行；新步骤只需在 _WIPE_MAP / _DISPATCH_MAP 各加一行。
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────
# ctx 完整重建
# ──────────────────────────────────────────────────────

def build_full_ctx(db: Session, project: Any) -> dict:
    """从 DB 完整重建 Bootstrap ctx，用于步骤独立重跑。

    覆盖字段：positioning / power / characters / factions / storylines /
              settings / volumes / villain_arc / opening_contract 等。

    Args:
        db: 数据库会话。
        project: Project ORM 对象。

    Returns:
        完整 ctx 字典；缺失字段保持默认值，不会引发 KeyError。
    """
    from app.models import Character, Faction, OutlineNode, PowerSystem, StoryLine, WorldSetting
    from app.services.bootstrap.power_registry import merge_power_into_ctx
    from app.services.outline_planning import words_to_plan

    project_id = str(project.id)
    target_words = int(project.target_words or 1_200_000)
    plan = words_to_plan(target_words)
    project_extra = project.extra if isinstance(project.extra, dict) else {}

    ctx: dict = {
        "logline": project.logline or "",
        "premise": project.premise or "",
        "target_words": target_words,
        "project_title": project.title or "未命名项目",
        "genre": project.genre or "玄幻",
        "project_genre": project.genre or "",
        "positioning": project_extra.get("positioning") or {},
        # 写作风格档位：单步重跑设定时仍按建书时选定的档位生成（否则 plain 书会退回 standard）
        "writing_style": project_extra.get("writing_style") or "standard",
        "chapter_quota_total": plan["total_chapters"],
        "chapter_quota_total_volumes": plan["total_volumes"],
        "chapter_quota_used": 0,
        # villain_arc 产物
        "villain_timelines": project_extra.get("villain_arc") or [],
        "antagonist_ladder": project_extra.get("antagonist_ladder") or [],
        "antagonist_ladder_summary": "",
        # opening_contract 产物
        "opening_contract": project_extra.get("opening_contract") or {},
    }

    if project_extra.get("antagonist_ladder"):
        from app.services.bootstrap.antagonist_roster import format_ladder_summary
        ctx["antagonist_ladder_summary"] = format_ladder_summary(project_extra["antagonist_ladder"])

    # ── 境界体系 ──────────────────────────────────────────────────────────
    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project_id)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    merge_power_into_ctx(ctx, pss, project=project)

    # ── 势力 ─────────────────────────────────────────────────────────────
    factions = (
        db.query(Faction)
        .filter(Faction.project_id == project_id)
        .order_by(Faction.name)
        .limit(20)
        .all()
    )
    if factions:
        ctx["faction_summary"] = "；".join(
            f"{f.name}（{(f.description or '')[:30]}）" for f in factions[:10]
        )

    # ── 故事线 ───────────────────────────────────────────────────────────
    storylines = (
        db.query(StoryLine)
        .filter(StoryLine.project_id == project_id)
        .all()
    )
    if storylines:
        ctx["storyline_summary"] = "；".join(
            f"{s.name}：{(s.description or '')[:50]}" for s in storylines[:10]
        )
        ctx["storyline_ids"] = {s.name: str(s.id) for s in storylines}
        ctx["relation_triggers"] = "；".join(
            s.name for s in storylines if s.line_type == "romance"
        ) or "（无）"

    # ── 人物库 ───────────────────────────────────────────────────────────
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

    # ── 设定卡 ───────────────────────────────────────────────────────────
    settings = (
        db.query(WorldSetting)
        .filter(WorldSetting.project_id == project_id)
        .limit(20)
        .all()
    )
    if settings:
        ctx["settings_summary"] = "；".join(
            f"{s.category}/{s.title}：{(s.content or '')[:60]}" for s in settings[:8]
        )

    # ── 卷骨架 ───────────────────────────────────────────────────────────
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
        # 统计已生成的章纲数（用于字数配额计数器）
        used = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
            )
            .count()
        )
        ctx["chapter_quota_used"] = used

    return ctx


# ──────────────────────────────────────────────────────
# 步骤产物清除
# ──────────────────────────────────────────────────────

def wipe_step(db: Session, project_id: str | UUID, step: str) -> None:
    """删除指定步骤的 DB 产物（幂等，失败时静默日志不抛出）。

    Args:
        db: 数据库会话。
        project_id: 项目 UUID（str 或 UUID 均可）。
        step: 步骤名（与 SSE event.step 一致）。
    """
    from app.models import (
        Character, CharacterRelationship, Faction, Foreshadow, Item,
        MemoryChunk, OutlineNode, PowerSystem, ReaderPromise, Scene, Skill, StoryLine, WorldSetting,
    )
    from sqlalchemy import or_

    pid = project_id if isinstance(project_id, UUID) else UUID(str(project_id))

    _WIPE_MAP: dict[str, Any] = {
        "power_systems":   PowerSystem,
        "factions":        Faction,
        "storylines":      StoryLine,
        "skills":          Skill,
        "items":           Item,
        "settings":        WorldSetting,
        "memory":          MemoryChunk,
        "core_mysteries":  Foreshadow,  # Bootstrap 生成的伏笔台账
    }
    if step in _WIPE_MAP:
        model = _WIPE_MAP[step]
        try:
            db.query(model).filter(model.project_id == pid).delete(synchronize_session=False)
            db.commit()
        except Exception:
            logger.exception("wipe_step(%s) failed", step)
            db.rollback()
        return

    if step == "antagonist_ladder":
        try:
            from app.models import Project as _Project
            from sqlalchemy.orm.attributes import flag_modified
            proj = db.query(_Project).filter(_Project.id == pid).first()
            if proj and isinstance(proj.extra, dict):
                extra = dict(proj.extra)
                extra.pop("antagonist_ladder", None)
                proj.extra = extra
                flag_modified(proj, "extra")
                db.commit()
        except Exception:
            logger.exception("wipe_step(antagonist_ladder) failed")
            db.rollback()
        return

    if step == "characters":
        try:
            ids = [r[0] for r in db.query(Character.id).filter(Character.project_id == pid).all()]
            if ids:
                db.query(CharacterRelationship).filter(
                    or_(
                        CharacterRelationship.from_character_id.in_(ids),
                        CharacterRelationship.to_character_id.in_(ids),
                    )
                ).delete(synchronize_session=False)
            db.query(Character).filter(Character.project_id == pid).delete(synchronize_session=False)
            db.commit()
        except Exception:
            logger.exception("wipe_step(characters) failed")
            db.rollback()

    elif step == "relations":
        try:
            db.query(CharacterRelationship).filter(
                CharacterRelationship.project_id == pid
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            logger.exception("wipe_step(relations) failed")
            db.rollback()

    elif step == "volumes":
        try:
            # 先删章纲子节点，再删卷节点，避免孤儿 FK
            vol_ids = [
                r[0]
                for r in db.query(OutlineNode.id)
                .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "volume")
                .all()
            ]
            if vol_ids:
                db.query(OutlineNode).filter(
                    OutlineNode.parent_id.in_(vol_ids)
                ).delete(synchronize_session=False)
            db.query(OutlineNode).filter(
                OutlineNode.project_id == pid, OutlineNode.node_type == "volume"
            ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            logger.exception("wipe_step(volumes) failed")
            db.rollback()

    elif step == "vol1_chapters":
        try:
            # 删第一卷的 chapter_plan 子节点 + Scene（若有）
            vol1 = (
                db.query(OutlineNode)
                .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "volume")
                .order_by(OutlineNode.sort_order)
                .first()
            )
            if vol1:
                plan_ids = [
                    r[0]
                    for r in db.query(OutlineNode.id)
                    .filter(OutlineNode.parent_id == vol1.id, OutlineNode.node_type == "chapter_plan")
                    .all()
                ]
                if plan_ids:
                    db.query(OutlineNode).filter(OutlineNode.id.in_(plan_ids)).delete(
                        synchronize_session=False
                    )
                # 清理卷级 linter 标记，使重跑后能重新 commit
                from sqlalchemy.orm.attributes import flag_modified
                extra = dict(vol1.extra or {})
                for k in ("linter_blocked", "linter_block_reason", "linter_user_message",
                          "linter_issues", "linter_status", "linter_summary"):
                    extra.pop(k, None)
                vol1.extra = extra
                flag_modified(vol1, "extra")
            db.commit()
        except Exception:
            logger.exception("wipe_step(vol1_chapters) failed")
            db.rollback()

    elif step == "ch1_scenes":
        try:
            ch1 = (
                db.query(OutlineNode)
                .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "chapter_plan")
                .order_by(OutlineNode.sort_order)
                .first()
            )
            if ch1:
                db.query(Scene).filter(
                    Scene.project_id == pid, Scene.outline_node_id == ch1.id
                ).delete(synchronize_session=False)
            db.commit()
        except Exception:
            logger.exception("wipe_step(ch1_scenes) failed")
            db.rollback()

    elif step in (
        "consistency", "opening_contract", "emotion_arc", "villain_arc",
        "rhythm_map", "signal_audit", "promise_seeds",
    ):
        # 这些步骤只写 project.extra，不删表行；由 dispatch_regen 覆盖写入即可
        _extra_keys = {
            "rhythm_map": ("rhythm_map",),
            "signal_audit": ("signal_audit",),
            "promise_seeds": ("core_mysteries", "opening_contract"),
        }
        keys = _extra_keys.get(step)
        if keys:
            try:
                from app.models import Project as _Project
                from sqlalchemy.orm.attributes import flag_modified
                proj = db.query(_Project).filter(_Project.id == pid).first()
                if proj and isinstance(proj.extra, dict):
                    extra = dict(proj.extra)
                    for k in keys:
                        extra.pop(k, None)
                    proj.extra = extra
                    flag_modified(proj, "extra")
                    db.commit()
            except Exception:
                logger.exception("wipe_step(%s) failed", step)
                db.rollback()

    else:
        logger.warning("wipe_step: 未知步骤 %s，跳过清理", step)


# ──────────────────────────────────────────────────────
# 步骤分发
# ──────────────────────────────────────────────────────

async def dispatch_regen(svc: Any, project: Any, step: str, ctx: dict) -> Any:
    """调用目标步骤的 gen_* 函数，返回产物（list 或 int）。

    Args:
        svc: GenerationService 实例。
        project: Project ORM 对象。
        step: 步骤名（与 SSE event.step 一致）。
        ctx: 完整 ctx 字典（由 build_full_ctx 重建）。

    Returns:
        步骤产物，通常是 list；若无产物返回 []。

    Raises:
        ValueError: 不支持的步骤名。
    """
    from app.models import OutlineNode, Character

    _SIMPLE_MAP: dict[str, str] = {
        "power_systems":    "_gen_power_systems",
        "factions":         "_gen_factions",
        "storylines":       "_gen_storylines",
        "antagonist_ladder": "_gen_antagonist_ladder",
        "settings":         "_gen_settings",
        "skills":           "_gen_key_skills",
        "items":            "_gen_key_items",
        "memory":           "_gen_memory",
        "opening_contract": "_gen_opening_contract",
        "core_mysteries":   "_gen_core_mysteries",
        "consistency":      "_gen_consistency_scan",
        "emotion_arc":      "_gen_emotion_arc",
        "villain_arc":      "_gen_villain_arc",
    }
    if step in _SIMPLE_MAP:
        fn = getattr(svc, _SIMPLE_MAP[step])
        result = await fn(project, ctx)
        return result if isinstance(result, list) else ([result] if result else [])

    if step == "characters":
        chars = await svc._gen_characters(project, ctx)
        if isinstance(chars, list):
            ctx["_char_ids"] = [str(c.id) for c in chars]
        return chars or []

    if step == "relations":
        chars = (
            svc.db.query(Character)
            .filter(Character.project_id == project.id)
            .all()
        )
        rels = await svc._gen_relations(project, chars, ctx)
        return rels or []

    if step == "volumes":
        extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
        if extra.get("fanfic_positioning"):
            from app.services.bootstrap.fanfic_ctx import merge_fanfic_extra_into_ctx

            merge_fanfic_extra_into_ctx(project, ctx)
        elif extra.get("fanqie_positioning") or extra.get("power_ladder"):
            from app.services.bootstrap.fanqie_ctx import merge_fanqie_extra_into_ctx

            merge_fanqie_extra_into_ctx(project, ctx)
        nodes = await svc._gen_volumes(project, ctx, inject_realm_fix_hint=True)
        if isinstance(nodes, list):
            ctx["_volume_ids"] = [str(n.id) for n in nodes]
            ctx["volumes_summary"] = " | ".join(
                f"{n.title}：{(n.summary or '')[:40]}" for n in nodes
            )
        return nodes or []

    if step in ("rhythm_map", "signal_audit", "promise_seeds"):
        extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
        if extra.get("fanqie_positioning") or extra.get("face_slap_map"):
            from app.services.bootstrap.fanqie_ctx import merge_fanqie_extra_into_ctx

            merge_fanqie_extra_into_ctx(project, ctx)
        if step == "rhythm_map":
            from app.services.bootstrap.steps.fanqie.rhythm_map import gen_rhythm_map

            data = await gen_rhythm_map(svc, project, ctx)
        elif step == "signal_audit":
            from app.services.bootstrap.steps.fanqie.signal_audit import gen_signal_audit

            data = await gen_signal_audit(svc, project, ctx)
        else:
            from app.services.bootstrap.steps.fanqie.promise_seeds import gen_promise_seeds

            data = await gen_promise_seeds(svc, project, ctx)
        return [data] if data else []

    raise ValueError(f"不支持的步骤：{step}")
