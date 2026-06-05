"""
番茄线境界统一策略 — 社会阶梯即全书唯一合法「主轴境界」。

设计动机：
  - 番茄 Bootstrap 用 power_ladder（社会五阶）而非通用 gen_power_systems；
  - 若不在卷纲/写章/复盘前注入同一套 canonical 名，模型会退回「筑基/金丹」套话；
  - 卷级 rank 须与 PowerSystem.levels[].rank（1-based）对齐，禁止 0-based 下标落库。

本模块供 Bootstrap ctx 注水、写章/预警 prompt、复盘落库规范化共用。
"""
from __future__ import annotations

from typing import Any

from app.routers.outline.helpers.constants import TRADITIONAL_CULTIVATION_BLACKLIST


def hydrate_fanqie_power_ctx(ctx: dict) -> dict:
    """
    从 ctx['power_ladder'] 注入 power_level_names / registry / power_systems_full，
    供 gen_volumes 与 protagonist_progression 在 converge 之前使用。
    """
    if ctx.get("power_level_names"):
        return ctx
    ladder = ctx.get("power_ladder")
    if not isinstance(ladder, dict):
        return ctx
    social = ladder.get("social_ladder")
    if not isinstance(social, list) or not social:
        return ctx

    names: list[str] = []
    registry: dict[str, dict[str, Any]] = {}
    levels: list[dict] = []
    for item in social:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        tier = item.get("tier")
        rank = int(tier) if isinstance(tier, int) and tier > 0 else len(names) + 1
        names.append(name)
        registry[name] = {"rank": rank, "axis": "primary", "raw_name": name}
        levels.append({
            "name": name,
            "rank": rank,
            "description": (item.get("description") or "").strip(),
            "representative": (item.get("representative") or "").strip(),
        })

    if not names:
        return ctx

    start_t = ladder.get("protagonist_start_tier")
    end_t = ladder.get("protagonist_end_tier")
    ctx["power_level_names"] = names
    ctx["power_level_registry"] = registry
    ctx["power_systems_full"] = [{
        "axis_role": "primary",
        "name": "社会权力阶梯",
        "levels": levels,
        "protagonist_current_rank": int(start_t) if isinstance(start_t, int) and start_t > 0 else 1,
        "protagonist_end_rank": int(end_t) if isinstance(end_t, int) and end_t > 0 else len(names),
        "description": (ladder.get("world_core_rule") or "").strip(),
    }]
    ctx.setdefault(
        "power_summary",
        "主轴（社会阶梯）：" + " → ".join(names),
    )
    return ctx


def primary_level_names_from_ctx_or_db(ctx: dict | None, db: Any, project_id: str) -> list[str]:
    """合法主轴境界名列表（低→高）。"""
    if ctx and ctx.get("power_level_names"):
        return list(ctx["power_level_names"])
    from app.models import PowerSystem
    from app.services.bootstrap.power_registry import primary_level_names

    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == project_id)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    return primary_level_names(pss) if pss else []


def build_fanqie_realm_discipline_block(level_names: list[str]) -> str:
    """写章/复盘/预警共用的境界铁律块。"""
    if not level_names:
        return ""
    ladder_line = " → ".join(level_names)
    banned = [
        t for t in TRADITIONAL_CULTIVATION_BLACKLIST
        if t and t not in ladder_line and t not in "".join(level_names)
    ]
    banned_sample = "、".join(banned[:12]) if banned else "筑基、金丹、元婴、化神等"
    return (
        "【番茄·主轴境界铁律（全书唯一合法大境，须与 PowerSystem 一致）】\n"
        f"合法大境（低→高，只能使用下列名称或其小境写法，如「{level_names[0]}初期」）：\n"
        f"  {ladder_line}\n"
        f"禁止在 current_realm / 正文 / 章纲中使用传统修真境名（如 {banned_sample}），"
        "除非该词已出现在上述合法列表中。\n"
        "小境写法：在合法大境后加「初期/中期/后期/圆满」（如「边陲小城弃民初期」），"
        "禁止单独写「筑基期」「炼气九层」等与本书阶梯无关的套话。\n"
        "复盘与写章：人物境界变化必须能映射到上述某一档大境。"
    )


def build_fanqie_realm_discipline_for_project(db: Any, project_id: str, ctx: dict | None = None) -> str:
    from app.models import Project
    from app.services.bootstrap.fanqie_normalize import is_fanqie_project

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not is_fanqie_project(project, ctx):
        return ""
    names = primary_level_names_from_ctx_or_db(ctx, db, project_id)
    if not names:
        tmp: dict = dict(ctx or {})
        extra = project.extra if isinstance(project.extra, dict) else {}
        tmp.setdefault("power_ladder", extra.get("power_ladder"))
        hydrate_fanqie_power_ctx(tmp)
        names = tmp.get("power_level_names") or []
    return build_fanqie_realm_discipline_block(names)


def normalize_realm_label_for_primary_axis(
    label: str,
    name_to_rank: dict[str, int],
) -> tuple[str, str | None]:
    """
    将复盘/模型输出的境界文本规范到主轴名。

    Returns:
        (canonical_label, warning_or_none)
    """
    s = (label or "").strip()
    if not s or not name_to_rank:
        return s, None
    if s in name_to_rank:
        return s, None

    for name in sorted(name_to_rank.keys(), key=len, reverse=True):
        if name in s:
            if s != name:
                return name, f"「{s}」已规范为主轴名「{name}」"
            return name, None

    for term in TRADITIONAL_CULTIVATION_BLACKLIST:
        if term and term in s and term not in name_to_rank:
            low_name = min(name_to_rank, key=lambda n: name_to_rank[n])
            return (
                low_name,
                f"「{s}」含传统境名「{term}」，已改为主轴最低档「{low_name}」",
            )

    return s, f"「{s}」未匹配主轴阶梯，请人工核对"


def ensure_protagonist_role(chars: list, *, preferred_name: str | None = None) -> None:
    """落库后保证恰好一名 protagonist（原地修改 Character.role）。"""
    if not chars:
        return
    protags = [c for c in chars if getattr(c, "role", None) == "protagonist"]
    if len(protags) == 1:
        return
    if len(protags) > 1:
        for c in protags[1:]:
            c.role = "supporting"
        return
    pick = None
    if preferred_name:
        pick = next((c for c in chars if c.name == preferred_name), None)
    if pick is None:
        pick = next(
            (c for c in chars if "主角" in (getattr(c, "author_notes", None) or "")),
            None,
        )
    if pick is None:
        pick = chars[0]
    pick.role = "protagonist"
