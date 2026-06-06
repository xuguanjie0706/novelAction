"""Bootstrap 境界体系 registry：多轴 PowerSystem → ctx 全保真注入。

P0 契约（下游只读这些键，禁止再手写 power_summary[:8] 截断逻辑）：
  - power_systems_full: 全部体系结构化快照（含 id / axis_role / levels）
  - power_level_registry: 境界名 → {system_id, rank, axis, system_name}
  - power_level_names: 主轴境界名列表（卷 BOSS 曲线兼容）
  - power_summary: 人类可读摘要（多轴概览，非截断）
"""

from __future__ import annotations

from typing import Any

from app.models import PowerSystem, Project

_AXIS_LABELS: dict[str, str] = {
    "primary": "修行主轴",
    "path": "道途",
    "artifact": "器物阶",
    "sect": "宗门位阶",
    "dao_heart": "道心",
    "social": "社会轴",
    "rule": "规则轴",
}


def axis_role_of(ps: PowerSystem) -> str:
    """从 PowerSystem.extra 读取轴角色，默认 primary。"""
    extra = ps.extra if isinstance(ps.extra, dict) else {}
    role = (extra.get("axis_role") or "primary").strip()
    return role or "primary"


def build_power_level_registry(power_systems: list[PowerSystem]) -> dict[str, dict[str, Any]]:
    """构建全局境界名 registry（跨轴唯一；重名时加体系前缀）。"""
    registry: dict[str, dict[str, Any]] = {}
    for ps in power_systems:
        sid = str(ps.id)
        axis = axis_role_of(ps)
        prefix = (ps.name or "").strip()
        for lv in ps.levels or []:
            if not isinstance(lv, dict):
                continue
            name = (lv.get("name") or "").strip()
            if not name:
                continue
            rank = lv.get("rank")
            key = name
            if key in registry and registry[key]["system_id"] != sid:
                key = f"{prefix}·{name}" if prefix else f"{axis}·{name}"
            registry[key] = {
                "system_id": sid,
                "rank": rank,
                "axis": axis,
                "system_name": ps.name or "",
                "raw_name": name,
            }
    return registry


def primary_level_names(power_systems: list[PowerSystem]) -> list[str]:
    """主轴境界名有序列表（低→高）。"""
    primary = next((ps for ps in power_systems if axis_role_of(ps) == "primary"), None)
    if primary is None and power_systems:
        primary = power_systems[0]
    if not primary:
        return []
    names: list[str] = []
    for lv in primary.levels or []:
        if isinstance(lv, dict) and (lv.get("name") or "").strip():
            names.append((lv.get("name") or "").strip())
    return names


def power_system_to_snapshot(ps: PowerSystem) -> dict[str, Any]:
    """单条 PowerSystem ORM → ctx 可序列化快照。"""
    extra = ps.extra if isinstance(ps.extra, dict) else {}
    return {
        "id": str(ps.id),
        "name": ps.name,
        "system_type": ps.system_type,
        "axis_role": axis_role_of(ps),
        "description": ps.description,
        "cultivation_method": ps.cultivation_method,
        "breakthrough_condition": ps.breakthrough_condition,
        "special_rules": ps.special_rules,
        "levels": ps.levels or [],
        "protagonist_current_rank": ps.protagonist_current_rank,
        "protagonist_end_rank": ps.protagonist_end_rank,
        "visualization": extra.get("visualization"),
        "path_id": extra.get("path_id"),
        "cross_system_rules": extra.get("cross_system_rules") or [],
    }


def format_power_context_block(ctx: dict) -> str:
    """供 prompt 注入的多轴境界上下文（替代单一 power_summary 行）。"""
    full = ctx.get("power_systems_full") or []
    laws = ctx.get("cultivation_laws") or {}
    if not full:
        return ctx.get("power_summary") or "（未设定境界体系）"

    lines: list[str] = ["【本书力量体系（多轴，须严格对齐）】"]
    if laws:
        rule = (laws.get("breakthrough_law") or laws.get("spirit_root_rule") or "").strip()
        if rule:
            lines.append(f"天地法则：{rule}")

    for snap in full:
        axis = snap.get("axis_role") or "primary"
        label = _AXIS_LABELS.get(axis, axis)
        levels = snap.get("levels") or []
        names = [
            (lv.get("name") or "").strip()
            for lv in levels
            if isinstance(lv, dict) and (lv.get("name") or "").strip()
        ]
        ladder = " → ".join(names) if names else "（无层级）"
        viz = (snap.get("visualization") or "").strip()
        lines.append(f"- [{label}] {snap.get('name', '')}：{ladder}")
        if viz:
            lines.append(f"  可视化：{viz}")

    registry = ctx.get("power_level_registry") or {}
    primary_names = ctx.get("power_level_names") or []
    if primary_names:
        lines.append(
            f"人物 current_realm 优先从修行主轴选择：{', '.join(primary_names)}"
        )
    if registry and len(registry) > len(primary_names):
        extra_keys = [k for k in registry if k not in primary_names][:12]
        if extra_keys:
            lines.append(f"副轴/位阶可选用：{', '.join(extra_keys)}")
    return "\n".join(lines)


def format_path_context_block(ctx: dict) -> str:
    """道途轴 prompt 块（供卷纲/技能使用）。"""
    paths = [
        s for s in (ctx.get("power_systems_full") or [])
        if s.get("axis_role") == "path"
    ]
    if not paths:
        return ""
    lines = ["【道途进阶轨（卷级 BOSS 须标注 volume_boss_path）】"]
    for p in paths:
        names = [
            (lv.get("name") or "").strip()
            for lv in (p.get("levels") or [])
            if isinstance(lv, dict) and (lv.get("name") or "").strip()
        ]
        pid = p.get("path_id") or p.get("name") or "path"
        lines.append(f"- {p.get('name', '')}（path_id={pid}）：{' → '.join(names)}")
    return "\n".join(lines)


def format_dao_heart_block(ctx: dict) -> str:
    """道心/渡劫映射 prompt 块。"""
    dao = ctx.get("dao_heart") or {}
    if not isinstance(dao, dict) or not dao:
        return ""
    lines = ["【道心/渡劫（至暗卷须触发心魔；大境突破须对号入座）】"]
    stages = dao.get("dao_heart_stages") or []
    if stages:
        lines.append(f"道心阶段：{' → '.join(stages[:6])}")
    trib = dao.get("tribulation_map") or {}
    if trib:
        lines.append(f"渡劫映射：{trib}")
    triggers = dao.get("heart_demon_triggers") or []
    if triggers:
        lines.append(f"心魔触发：{'、'.join(triggers[:5])}")
    return "\n".join(lines)


def _realm_core(name: str) -> str:
    """去掉小境界/境后缀，便于「筑基中期」→「筑基境」匹配。"""
    s = name.strip()
    for chop in ("初期", "中期", "后期", "圆满", "境", "期", "层", "重"):
        s = s.replace(chop, "")
    return s.strip()


def resolve_realm_in_registry(realm: str | None, registry: dict[str, dict[str, Any]]) -> str | None:
    """模糊匹配 registry 中的 canonical 境界名；无法匹配返回 None。"""
    if not realm or not registry:
        return None
    s = realm.strip()
    if not s:
        return None
    if s in registry:
        return s
    core_s = _realm_core(s)
    for key, meta in registry.items():
        raw = (meta.get("raw_name") or key).strip()
        if raw and (raw in s or s in raw or key in s or s in key):
            return key
        if core_s and _realm_core(raw) == core_s:
            return key
        if core_s and core_s in _realm_core(raw):
            return key
    return None


def merge_power_into_ctx(
    ctx: dict,
    power_systems: list[PowerSystem],
    *,
    project: Project | None = None,
    cultivation_laws: dict | None = None,
    dao_heart: dict | None = None,
) -> None:
    """将 PowerSystem 列表与修仙扩展写入 ctx（原地更新）。"""
    if cultivation_laws is not None:
        ctx["cultivation_laws"] = cultivation_laws
    elif project is not None:
        extra = project.extra if isinstance(project.extra, dict) else {}
        if extra.get("cultivation_laws"):
            ctx["cultivation_laws"] = extra["cultivation_laws"]
    if dao_heart is not None:
        ctx["dao_heart"] = dao_heart
    elif project is not None:
        extra = project.extra if isinstance(project.extra, dict) else {}
        if extra.get("dao_heart"):
            ctx["dao_heart"] = extra["dao_heart"]

    if not power_systems:
        ctx["power_systems_full"] = []
        ctx["power_level_registry"] = {}
        ctx["power_level_names"] = []
        ctx["power_system_name"] = ""
        ctx["power_summary"] = "（本项目尚未录入境界体系，设定卡可自行铺垫力量氛围，勿展开成完整境界表）"
        return

    snapshots = [power_system_to_snapshot(ps) for ps in power_systems]
    registry = build_power_level_registry(power_systems)
    primary_names = primary_level_names(power_systems)

    ctx["power_systems_full"] = snapshots
    ctx["power_level_registry"] = registry
    ctx["power_level_names"] = primary_names

    primary_ps = next((ps for ps in power_systems if axis_role_of(ps) == "primary"), power_systems[0])
    ctx["power_system_name"] = primary_ps.name or ""

    axis_parts: list[str] = []
    for snap in snapshots:
        axis = snap.get("axis_role") or "primary"
        label = _AXIS_LABELS.get(axis, axis)
        levels = snap.get("levels") or []
        n = len([lv for lv in levels if isinstance(lv, dict) and lv.get("name")])
        axis_parts.append(f"{label}「{snap.get('name', '')}」{n}层")
    ctx["power_summary"] = "；".join(axis_parts)
    if primary_names:
        ctx["power_summary"] += "｜主轴：" + " → ".join(primary_names)


def build_draft_power_context_from_db(db: Any, project_id: Any) -> str:
    """
    写章/质检路径：从 DB 组装多轴力量体系全文（替代 power_summary 截断）。

    供 gated_draft、quality、context_builder 等统一调用。
    """
    from app.models import PowerSystem, Project

    pid = str(project_id)
    project = db.query(Project).filter(Project.id == pid).first()
    pss = (
        db.query(PowerSystem)
        .filter(PowerSystem.project_id == pid)
        .order_by(PowerSystem.sort_order)
        .all()
    )
    if not pss:
        return "（未设定境界体系）"

    ctx: dict = {}
    merge_power_into_ctx(ctx, pss, project=project)
    parts: list[str] = [format_power_context_block(ctx)]

    dao_block = format_dao_heart_block(ctx)
    if dao_block:
        parts.append(dao_block)

    extra = project.extra if project and isinstance(project.extra, dict) else {}
    laws = extra.get("cultivation_laws") if isinstance(extra.get("cultivation_laws"), dict) else {}
    if laws:
        law_lines = ["【天地法则（写章不可违反）】"]
        for key, label in (
            ("spirit_root_rule", "灵根/资质"),
            ("breakthrough_law", "突破/渡劫"),
            ("ascension_rule", "飞升/位面上限"),
            ("golden_finger_cost", "金手指代价"),
        ):
            val = (laws.get(key) or "").strip()
            if val:
                law_lines.append(f"- {label}：{val}")
        if len(law_lines) > 1:
            parts.append("\n".join(law_lines))

    parts.append(
        "【写章铁律】人物境界/器物/道途须与上述 registry 对齐；"
        "禁止越境施法、未渡劫强行突破、道途与宗门设定矛盾。"
    )
    from app.services.bootstrap.fanqie_normalize import is_fanqie_project
    from app.services.bootstrap.fanqie_realm_policy import build_fanqie_realm_discipline_block

    if project and is_fanqie_project(project):
        _extra = project.extra if isinstance(project.extra, dict) else {}
        _axis_kind = (
            (ctx or {}).get("fanqie_axis_kind")
            or _extra.get("fanqie_axis_kind")
            or (_extra.get("power_ladder") or {}).get("axis_kind")
            or "social"
        )
        fanqie_block = build_fanqie_realm_discipline_block(
            ctx.get("power_level_names") or [], axis_kind=_axis_kind,
        )
        if fanqie_block:
            parts.append(fanqie_block)
    return "\n\n".join(parts)

