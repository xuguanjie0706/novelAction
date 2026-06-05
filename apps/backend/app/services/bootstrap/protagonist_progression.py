"""主角跨卷境界成长曲线：计算、落库兜底与 prompt 格式化。"""
from __future__ import annotations

from app.services.bootstrap.power_registry import resolve_realm_in_registry


def _build_rank_map_from_ctx(ctx: dict, level_names: list[str]) -> dict[str, int]:
    """境界名 → PowerSystem rank（1-based）；无 registry 时按 level_names 顺序生成。"""
    registry: dict = ctx.get("power_level_registry") or {}
    rank_map: dict[str, int] = {}
    if registry:
        for name, meta in registry.items():
            if isinstance(meta, dict) and isinstance(meta.get("rank"), int) and meta["rank"] > 0:
                r = int(meta["rank"])
                if name not in rank_map or r > rank_map[name]:
                    rank_map[name] = r
    if not rank_map:
        rank_map = {name: i + 1 for i, name in enumerate(level_names)}
    return rank_map


def _realm_display_at_rank(rank: int, level_names: list[str], rank_map: dict[str, int]) -> str:
    """1-based rank → 境界展示名（与 realm_axis / PowerSystem 一致）。"""
    if rank <= 0:
        return ""
    inverse = {v: k for k, v in rank_map.items()}
    if rank in inverse:
        return inverse[rank]
    if rank <= len(level_names):
        return level_names[rank - 1]
    return level_names[-1] if level_names else ""


def compute_book_realm_endpoints(ctx: dict) -> tuple[int, int, list[str]] | None:
    """计算全书主角起点/终点 rank。

    Returns:
        (start_rank, end_rank, level_names)，无法计算时返回 None。
    """
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    if not level_names:
        return None

    rank_map = _build_rank_map_from_ctx(ctx, level_names)
    registry: dict = ctx.get("power_level_registry") or {}
    max_rank = max(rank_map.values()) if rank_map else len(level_names)

    protagonist = (ctx.get("protagonist") or "主角").strip()
    start_rank = 1
    protag_realm = (ctx.get("char_realms") or {}).get(protagonist, "")
    if protag_realm:
        resolved = resolve_realm_in_registry(protag_realm, registry) if registry else protag_realm
        start_rank = rank_map.get(resolved or protag_realm, 1)

    end_rank = max_rank
    for snap in ctx.get("power_systems_full") or []:
        if (snap.get("axis_role") or "primary") == "primary":
            er = snap.get("protagonist_end_rank")
            if isinstance(er, int) and 0 <= er <= max_rank:
                end_rank = er
            break

    if end_rank <= start_rank:
        return None
    return start_rank, end_rank, level_names


def compute_vol_end_ranks(ctx: dict, n_volumes: int) -> list[int] | None:
    """线性插值分配各卷末主角预期 rank。"""
    if n_volumes <= 0:
        return None
    endpoints = compute_book_realm_endpoints(ctx)
    if not endpoints:
        return None
    start_rank, end_rank, _ = endpoints
    total_growth = end_rank - start_rank
    vol_end_ranks: list[int] = []
    for vi in range(n_volumes):
        frac = (vi + 1) / n_volumes
        raw = start_rank + frac * total_growth
        vol_end_ranks.append(min(int(raw), end_rank))
    vol_end_ranks[-1] = end_rank
    return vol_end_ranks


def _resolve_realm_rank_simple(
    realm_name: str | None,
    rank_map: dict[str, int],
    level_names: list[str],
    registry: dict,
) -> int:
    if not realm_name or not str(realm_name).strip():
        return -1
    name = str(realm_name).strip()
    resolved = resolve_realm_in_registry(name, registry) if registry else name
    canonical = resolved or name
    if canonical in rank_map:
        return rank_map[canonical]
    for ln in sorted(level_names, key=len, reverse=True):
        if ln and (ln in canonical or canonical in ln):
            return rank_map.get(ln, -1)
    return -1


def vol_protagonist_realm_bounds(
    vol_index: int,
    vol_end_ranks: list[int],
    level_names: list[str],
    book_start_rank: int,
    rank_map: dict[str, int],
) -> tuple[str, str, int, int]:
    """单卷主角境界起止（canonical 名 + 1-based rank）。"""
    start_rank = book_start_rank if vol_index == 0 else vol_end_ranks[vol_index - 1]
    end_rank = vol_end_ranks[vol_index]
    return (
        _realm_display_at_rank(start_rank, level_names, rank_map),
        _realm_display_at_rank(end_rank, level_names, rank_map),
        start_rank,
        end_rank,
    )


def apply_volume_protagonist_fields(
    vol: dict,
    vol_extra: dict,
    vol_index: int,
    ctx: dict,
    n_volumes: int,
) -> None:
    """将主角境界起止写入 vol_extra；AI 漏填时用插值曲线兜底。"""
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    if not level_names:
        return

    rank_map = _build_rank_map_from_ctx(ctx, level_names)
    registry: dict = ctx.get("power_level_registry") or {}
    endpoints = compute_book_realm_endpoints(ctx)
    vol_end_ranks = compute_vol_end_ranks(ctx, n_volumes)

    fallback_start, fallback_end, fb_start_rank, fb_end_rank = "", "", -1, -1
    if endpoints and vol_end_ranks and vol_index < len(vol_end_ranks):
        book_start, _, _ = endpoints
        fallback_start, fallback_end, fb_start_rank, fb_end_rank = vol_protagonist_realm_bounds(
            vol_index, vol_end_ranks, level_names, book_start, rank_map,
        )

    ai_start = (vol.get("protagonist_realm_start") or "").strip()
    ai_end = (vol.get("protagonist_realm_end") or "").strip()
    start_rank = _resolve_realm_rank_simple(ai_start, rank_map, level_names, registry)
    end_rank = _resolve_realm_rank_simple(ai_end, rank_map, level_names, registry)

    if start_rank < 1 and fb_start_rank >= 1:
        start_rank, ai_start = fb_start_rank, fallback_start
    elif start_rank >= 1:
        ai_start = _realm_display_at_rank(start_rank, level_names, rank_map)

    if end_rank < 1 and fb_end_rank >= 1:
        end_rank, ai_end = fb_end_rank, fallback_end
    elif end_rank >= 1:
        ai_end = _realm_display_at_rank(end_rank, level_names, rank_map)

    if start_rank >= 1 and end_rank >= 1 and end_rank < start_rank:
        end_rank, ai_end = start_rank, ai_start

    if ai_start:
        vol_extra["protagonist_realm_start"] = ai_start
    if ai_end:
        vol_extra["protagonist_realm_end"] = ai_end
    if start_rank >= 1:
        vol_extra["protagonist_realm_start_rank"] = start_rank
    if end_rank >= 1:
        vol_extra["protagonist_realm_end_rank"] = end_rank


def build_protagonist_progression_prompt_block(ctx: dict, n_volumes: int) -> str:
    """生成 Step 9 prompt 主角成长路线约束块。"""
    endpoints = compute_book_realm_endpoints(ctx)
    vol_end_ranks = compute_vol_end_ranks(ctx, n_volumes)
    if not endpoints or not vol_end_ranks:
        return ""

    start_rank, end_rank, level_names = endpoints
    rank_map = _build_rank_map_from_ctx(ctx, level_names)
    max_rank = max(rank_map.values()) if rank_map else len(level_names)
    protagonist = (ctx.get("protagonist") or "主角").strip()

    lines: list[str] = [
        "\n【⚠️ 主角境界成长路线（必须严格遵守）】",
        (
            f"主角「{protagonist}」：起点 {_realm_display_at_rank(start_rank, level_names, rank_map)}（rank={start_rank}）"
            f" → 全书终点 {_realm_display_at_rank(end_rank, level_names, rank_map)}（rank={end_rank}）"
        ),
        "各卷须填写 protagonist_realm_start / protagonist_realm_end（须从境界阶梯精确选名）：",
    ]
    book_start = start_rank
    for vi, vr in enumerate(vol_end_ranks):
        sr = book_start if vi == 0 else vol_end_ranks[vi - 1]
        boss_max_rank = min(vr + 2, max_rank)
        lines.append(
            f"  第{vi + 1}卷：{_realm_display_at_rank(sr, level_names, rank_map)} → {_realm_display_at_rank(vr, level_names, rank_map)}"
            f"（rank {sr}→{vr}）| volume_boss_realm rank 上限 {_realm_display_at_rank(boss_max_rank, level_names, rank_map)}（{boss_max_rank}）"
        )
    lines.append(
        "⚠️ 每卷 volume_boss_realm 的 rank 严格 ≤ protagonist_realm_end 对应 rank + 2；"
        "主角能靠努力/觉醒赢，但不能凭空跨越三档以上。"
    )
    lines.append(
        f"⚠️ 终局卷（phase=climax 或 ending）的 volume_boss_realm 必须处于"
        f" {_realm_display_at_rank(max(end_rank - 1, 1), level_names, rank_map)} 或 {_realm_display_at_rank(end_rank, level_names, rank_map)}，"
        f"禁止终局 Boss 停留在中低档境界（rank < {end_rank - 1}）。"
    )
    return "\n".join(lines) + "\n"


def build_protagonist_backfill_ctx(db: Any, project_id: str) -> dict | None:
    """从 DB 组装 apply_volume_protagonist_fields 所需的最小 ctx（存量项目补全用）。"""
    from app.models import Character, PowerSystem, Project
    from app.services.bootstrap.power_registry import merge_power_into_ctx

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None

    power_systems = (
        db.query(PowerSystem).filter(PowerSystem.project_id == project_id).all()
    )
    ctx: dict = {"protagonist": "主角", "char_realms": {}}
    chars = db.query(Character).filter(Character.project_id == project_id).all()
    protag = next((c for c in chars if getattr(c, "role", None) == "protagonist"), None)
    if protag and protag.name:
        ctx["protagonist"] = protag.name.strip()
        realm = (getattr(protag, "current_realm", None) or "").strip()
        if realm:
            ctx["char_realms"][protag.name] = realm

    merge_power_into_ctx(ctx, power_systems, project=project)
    if not ctx.get("power_level_names"):
        return None
    return ctx


def backfill_volume_protagonist_realms(db: Any, project_id: str) -> int:
    """为缺 protagonist_realm_* 的卷节点按境界阶梯插值补全（幂等）。

    Returns:
        实际更新的卷数量。
    """
    from app.models import OutlineNode
    from sqlalchemy.orm.attributes import flag_modified

    ctx = build_protagonist_backfill_ctx(db, project_id)
    if not ctx:
        return 0

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order, OutlineNode.created_at)
        .all()
    )
    if not volumes:
        return 0

    if all((v.extra or {}).get("protagonist_realm_end") for v in volumes):
        return 0

    n = len(volumes)
    updated = 0
    for i, vol in enumerate(volumes):
        extra = dict(vol.extra or {})
        if (extra.get("protagonist_realm_start") or "").strip() and (
            extra.get("protagonist_realm_end") or ""
        ).strip():
            continue
        vol_ai = {
            "protagonist_realm_start": extra.get("protagonist_realm_start"),
            "protagonist_realm_end": extra.get("protagonist_realm_end"),
        }
        apply_volume_protagonist_fields(vol_ai, extra, i, ctx, n)
        if (extra.get("protagonist_realm_end") or "").strip():
            vol.extra = extra
            flag_modified(vol, "extra")
            updated += 1

    if updated:
        db.commit()
    return updated


def format_volume_realm_anchor_line(extra: dict | None) -> str:
    """全卷骨架展示用：主角境界路线 + BOSS 境界。"""
    ex = extra if isinstance(extra, dict) else {}
    start = (ex.get("protagonist_realm_start") or "").strip()
    end = (ex.get("protagonist_realm_end") or "").strip()
    boss = (ex.get("volume_boss_realm") or "").strip()
    parts: list[str] = []
    if start and end:
        parts.append(f"主角 {start}→{end}")
    elif end:
        parts.append(f"主角卷末 {end}")
    if boss:
        parts.append(f"BOSS {boss}")
    return " | ".join(parts)
