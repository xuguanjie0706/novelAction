"""Bootstrap 上下文拼装：genre_kit 注入块、从已落库 Project 还原 Step 近似 ctx。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Character, Faction, PowerSystem, Project
from app.services.genre_kit import get_genre_kit, normalize_genre, render_kit_for_prompt


def get_genre_kit_block(ctx: dict) -> str:
    """返回 genre_kit 的 prompt 注入块；ctx 已有 ``genre_kit_prompt`` 则优先使用。"""
    kit_prompt = ctx.get("genre_kit_prompt")
    if kit_prompt:
        return f"\n{kit_prompt}\n"
    genre = ctx.get("genre")
    if genre:
        from app.services.genre_kit import get_genre_guardrail

        return "\n" + get_genre_guardrail(genre) + "\n"
    return ""


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
    if pss:
        main_ps = pss[0]
        level_names = [
            lv.get("name", "")
            for lv in (main_ps.levels or [])
            if isinstance(lv, dict) and lv.get("name")
        ]
        ctx["power_level_names"] = level_names
        ctx["power_system_name"] = main_ps.name
        ctx["power_summary"] = f"{main_ps.name}：" + " → ".join(level_names[:8])
    else:
        ctx["power_level_names"] = []
        ctx["power_system_name"] = ""
        ctx["power_summary"] = "（本项目尚未录入境界体系，设定卡可自行铺垫力量氛围，勿展开成完整境界表）"

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
