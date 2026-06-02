"""Bootstrap 上下文拼装：genre_kit 注入块、从已落库 Project 还原 Step 近似 ctx。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Character, Faction, PowerSystem, Project
from app.services.bootstrap.power_registry import merge_power_into_ctx
from app.services.genre_kit import get_genre_kit, normalize_genre, render_kit_for_prompt


def _writing_style_block(ctx: dict) -> str:
    """白话直白档的设定简化约束块；非 plain 档返回空串（行为不变）。

    作者建书时选 ``writing_style=plain`` 时，在所有设定生成步骤（境界 / 势力 / 技能 /
    道具 / 设定卡等，均经 get_genre_kit_block 注入）追加「降低阅读门槛」的硬约束，
    从源头控制设定复杂度，而非只在正文层补救。
    """
    if str(ctx.get("writing_style") or "").strip().lower() != "plain":
        return ""
    return (
        "【白话直白模式 · 设定须降低阅读门槛】\n"
        "- 命名用大白话：境界名、功法名、势力名、专有名词尽量好认好记，少用生僻字与古奥词藻。\n"
        "- 层级要克制：境界 / 等级体系层数宁少勿多（建议不超过 6~7 层），避免读者记不住。\n"
        "- 每个专有名词都要有一句通俗解释：description 用读者一眼能懂的话说明「它是什么、有多强」。\n"
        "- 控制数量：同一体系下并列概念不要过多，优先少而清晰。\n"
    )


def get_genre_kit_block(ctx: dict) -> str:
    """返回 genre_kit 的 prompt 注入块；ctx 已有 ``genre_kit_prompt`` 则优先使用。

    若 ``ctx['writing_style'] == 'plain'``，额外追加设定简化约束块（降低阅读门槛）。
    """
    style_block = _writing_style_block(ctx)
    kit_prompt = ctx.get("genre_kit_prompt")
    if kit_prompt:
        return f"\n{kit_prompt}\n{style_block}"
    genre = ctx.get("genre")
    if genre:
        from app.services.genre_kit import get_genre_guardrail

        return "\n" + get_genre_guardrail(genre) + "\n" + style_block
    return ("\n" + style_block) if style_block else ""


def hydrate_ctx_from_project(db: Session, project: Project) -> dict:
    """
    从已落库项目拼装与 Bootstrap Step8 相近的 ctx，供「补生成设定卡」类接口复用。

    不假设项目一定已有境界/势力/人物；缺失时写入占位说明，避免 prompt 空白。
    """
    sc = project.story_core
    if not isinstance(sc, dict):
        sc = {}
    genre = project.genre or "玄幻"
    ctx: dict = {
        "logline": project.logline or "",
        "premise": project.premise or "",
        "target_words": int(project.target_words or 1_200_000),
        "project_title": project.title or "未命名",
        "genre": genre,
        "world_overview": project.world_overview or "",
        "story_core": sc,
        # 写作风格档位：补生成设定卡时沿用建书时选定的档位（plain 时降低阅读门槛）
        "writing_style": (
            (project.extra or {}).get("writing_style")
            if isinstance(project.extra, dict) else None
        ) or "standard",
    }
    kit = get_genre_kit(normalize_genre(genre))
    ctx["genre_kit"] = kit
    ctx["genre_kit_prompt"] = render_kit_for_prompt(kit)

    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project.id)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    merge_power_into_ctx(ctx, pss, project=project)

    facs = (
        db.query(Faction)
        .filter(Faction.project_id == project.id)
        .order_by(Faction.sort_order)
        .all()
    )
    if facs:
        ctx["faction_summary"] = "、".join(
            f"{f.name}（{f.alignment}，{(f.extra or {}).get('active_period', '')}期）"
            for f in facs
        )
        ctx["faction_names"] = [f.name for f in facs]
    else:
        ctx["faction_summary"] = "（本项目尚未录入势力档案，勿整段复制势力全书式档案）"
        ctx["faction_names"] = []

    chars = (
        db.query(Character)
        .filter(Character.project_id == project.id)
        .order_by(Character.created_at)
        .all()
    )
    ctx["char_names"] = [c.name for c in chars[:40]]
    protag = next((c.name for c in chars if c.role == "protagonist"), None)
    ctx["protagonist"] = protag or (chars[0].name if chars else "主角")
    return ctx
