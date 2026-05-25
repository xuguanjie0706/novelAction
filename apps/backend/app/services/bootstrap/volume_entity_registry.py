"""卷级骨架实体登记表：生成约束 + 落库后确定性校验。

Bootstrap Step 9 此前未注入势力/境界 canonical 列表，模型易在卷 summary 中
自创「云霄剑宗」「冥府」等别名，与 Step 3/5 档案漂移。本模块提供：
- build_volume_entity_prompt_block：写入 gen_volumes prompt
- lint_volume_entity_issues：纯代码交叉核验（供 consistency_scan 预检复用）
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services.bootstrap.power_registry import (
    format_dao_heart_block,
    format_path_context_block,
)

_ORG_SUFFIX_CHARS = frozenset("宗殿堂府家门阁派盟宫国城谷岛会帮")
# 组织名前缀不应以叙事动词/介词开头（避免「拜入云霄剑宗」整段被吞）
_ORG_BAD_PREFIX_RE = re.compile(
    r"^[与攻拜入归投赴袭灭屠诸各其于在从向对和及]"
)

# 卷末/终局 Boss 常见称谓片段
_BOSS_HINT_RE = re.compile(r"(?:冥皇|魔尊|天帝|仙帝|至尊|主宰|大魔|终极|最终)")

# 卷级核心对立面常见叙事词（领袖/幕后/终战对手等，不限 role=antagonist）
_VOL_THREAT_HINT_RE = re.compile(
    r"(?:领袖|首领|BOSS|boss|魔头|幕后|终战|对决|宿敌|大反派|反派|魔尊|殿主|宗主|掌门)"
)

_REALM_NEAR_NAME_RE = re.compile(
    r"[\(（]([^）\)]{2,8})[\)）]|"
    r"(?:为|达|至|已是|突破至|晋入)\s*([\u4e00-\u9fff]{2,8})"
)

# 结构化字段 / 叙述中「名+境界」模式
_NAME_REALM_PAREN_RE = re.compile(
    r"([\u4e00-\u9fff]{2,4})[\(（]([\u4e00-\u9fff]{2,8})[\)）]"
)


def build_volume_entity_prompt_block(ctx: dict) -> str:
    """拼装卷级生成必须遵守的实体登记表（势力名 + 人物归属 + 境界阶梯）。"""
    faction_names: list[str] = list(ctx.get("faction_names") or [])
    if not faction_names and ctx.get("faction_summary"):
        faction_names = [
            p.split("（")[0].strip()
            for p in str(ctx["faction_summary"]).split("、")
            if p.strip()
        ]

    level_names: list[str] = list(ctx.get("power_level_names") or [])
    lines: list[str] = []

    if faction_names:
        lines.append("【势力登记表 — 卷级 summary/conflict 中提及组织时只能使用下列名称，禁止同义替换】")
        for fn in faction_names:
            lines.append(f"  - {fn}")
        lines.append(
            "  ⚠️ 禁止自创别名（如档案为「凌云宗」则不得写「云霄剑宗」；"
            "档案为「噬魂殿」则不得写「冥府」）。"
        )

    char_realms: dict = ctx.get("char_realms") or {}
    protagonist = (ctx.get("protagonist") or "主角").strip()
    if char_realms:
        lines.append("【人物+境界登记表 — 卷级提及下列人物时须使用档案境界，后期卷反派不得低于前期卷】")
        for name, realm in char_realms.items():
            tier = ""
            if name == protagonist:
                tier = "主角"
            lines.append(f"  - {name}（{tier or '人物'}）：{realm}")
        antagonists = [
            (n, r) for n, r in char_realms.items() if n != protagonist and _looks_antagonist(ctx, n)
        ]
        if antagonists:
            lines.append(
                "  ⚠️ 反派境界曲线：越靠后的卷，当卷核心反派 effective 境界 rank 须严格高于前期卷；"
                "禁止后期卷 BOSS 境界低于前期卷（如卷四领袖低于卷三 BOSS 是致命低级错误）。"
            )

    if level_names:
        top = level_names[-1]
        second = level_names[-2] if len(level_names) >= 2 else top
        lines.append(f"【境界阶梯（低→高，rank 0→{len(level_names) - 1}）】{' → '.join(level_names)}")
        lines.append(
            "  ⚠️ 每卷必填 volume_boss（当卷核心对立角色名）与 volume_boss_realm（必须从上方阶梯精确选名）；"
            "volume_boss_realm 的 rank 须严格单调递增（后卷 rank > 前卷 rank）。"
        )
        lines.append(
            f"  ⚠️ 全书终局对立面须处于「{second}」或最高档「{top}」，"
            f"禁止终局 Boss 仅停留在中阶境界。"
        )

    path_block = format_path_context_block(ctx)
    if path_block:
        lines.append(path_block)
        lines.append(
            "  ⚠️ 每卷建议填写 volume_boss_path（道途 path_id 或道途名）与 volume_boss_path_rank（道途阶位精确名）；"
            "后卷 BOSS 道途阶 rank 宜 ≥ 前卷（与境界曲线同向）。"
        )

    dao_block = format_dao_heart_block(ctx)
    if dao_block:
        lines.append(dao_block)
        lines.append("  ⚠️ phase=dark_hour 的卷须在 summary 中体现心魔/红尘劫/道心考验。")

    protag_faction = _protagonist_faction_from_ctx(ctx)
    if protagonist and protag_faction and "家" in protag_faction:
        surname = protagonist[0] if protagonist else ""
        if surname and surname not in protag_faction:
            lines.append(
                f"【血缘/归属约束】主角「{protagonist}」所属「{protag_faction}」："
                f"卷级叙述若强调血缘须与姓氏一致；若为养子/外姓传人须在 summary 中点明，"
                f"勿让读者误以为同姓血亲。"
            )

    if not lines:
        return ""
    return "\n" + "\n".join(lines) + "\n"


def _looks_antagonist(ctx: dict, name: str) -> bool:
    hints = " ".join(
        str(x) for x in (
            ctx.get("villain_timelines") or [],
            ctx.get("villain_arc_summary") or "",
        )
    )
    return name in hints or "反派" in hints


def _protagonist_faction_from_ctx(ctx: dict) -> str:
    pf = ctx.get("protagonist_faction")
    if pf:
        return str(pf).strip()
    protag = (ctx.get("protagonist") or "").strip()
    for line in (ctx.get("character_faction_lines") or []):
        if protag and protag in line:
            return line.split("：", 1)[-1].strip() if "：" in line else ""
    return ""


def _build_realm_rank_map(level_names: list[str]) -> dict[str, int]:
    return {name: i for i, name in enumerate(level_names) if name}


def _resolve_realm_rank(
    realm_name: str | None,
    rank_map: dict[str, int],
    level_names: list[str],
) -> int:
    """将境界名映射为 rank；支持子串模糊（如「初期灵台境」→「灵台境」）。"""
    if not realm_name:
        return -1
    realm_name = realm_name.strip()
    if realm_name in rank_map:
        return rank_map[realm_name]
    for ln in sorted(level_names, key=len, reverse=True):
        if ln and (ln in realm_name or realm_name in ln):
            return rank_map.get(ln, -1)
    return -1


def _char_effective_rank(
    char: Any,
    blob: str,
    level_names: list[str],
    rank_map: dict[str, int],
) -> int:
    """人物在卷叙述中的 effective 境界 rank（优先卷内明示，其次档案）。"""
    if not char or not getattr(char, "name", None):
        return -1
    realm = _extract_realm_near_name(blob, char.name, level_names)
    r = _resolve_realm_rank(realm, rank_map, level_names)
    if r >= 0:
        return r
    if getattr(char, "realm_rank", None) is not None:
        return int(char.realm_rank)
    return _resolve_realm_rank(getattr(char, "current_realm", None), rank_map, level_names)


def _volume_structured_boss(vol: Any, rank_map: dict[str, int], level_names: list[str]) -> tuple[str, int]:
    """从 volume.extra 读取结构化 BOSS 字段。"""
    extra = getattr(vol, "extra", None) or {}
    if not isinstance(extra, dict):
        return "", -1
    boss = (extra.get("volume_boss") or extra.get("volume_antagonist") or "").strip()
    realm = (extra.get("volume_boss_realm") or "").strip()
    r = _resolve_realm_rank(realm, rank_map, level_names)
    return boss, r


def _volume_peak_threat(
    vol: Any,
    chars: list[Any],
    protagonist: str,
    level_names: list[str],
    rank_map: dict[str, int],
) -> tuple[str, int]:
    """估算当卷核心威胁角色的最高 effective 境界 rank。"""
    blob = " ".join(filter(None, [vol.title, vol.summary, vol.conflict, vol.hook]))
    peak_name = ""
    peak_rank = -1

    boss, boss_rank = _volume_structured_boss(vol, rank_map, level_names)
    if boss_rank >= 0:
        peak_name, peak_rank = boss, boss_rank

    for char in chars:
        name = (getattr(char, "name", None) or "").strip()
        if not name or name == protagonist or name not in blob:
            continue
        role = (getattr(char, "role", None) or "").strip()
        tier = (getattr(char, "character_tier", None) or "").strip()
        if role == "protagonist":
            continue
        # 主角以外：反派 / 弧线支柱 / 核心角色，或叙述中带威胁词
        is_threat = role == "antagonist" or tier in ("core", "arc")
        if not is_threat:
            idx = blob.find(name)
            window = blob[max(0, idx - 6): idx + len(name) + 24] if idx >= 0 else ""
            is_threat = bool(_VOL_THREAT_HINT_RE.search(window))
        if not is_threat:
            continue
        r = _char_effective_rank(char, blob, level_names, rank_map)
        if r > peak_rank:
            peak_rank, peak_name = r, name

    # 「沈苍海（命轮境）」类叙述：卷内未建档角色也须纳入
    for m in _NAME_REALM_PAREN_RE.finditer(blob):
        nm, realm_raw = m.group(1), m.group(2)
        if nm == protagonist:
            continue
        r = _resolve_realm_rank(realm_raw, rank_map, level_names)
        if r > peak_rank:
            peak_rank, peak_name = r, nm

    return peak_name, peak_rank


def _volume_boss_path_rank(vol: Any, registry: dict[str, dict]) -> tuple[str, int]:
    """从 volume.extra 读取 BOSS 道途阶 rank。"""
    from app.services.bootstrap.power_registry import resolve_realm_in_registry

    extra = getattr(vol, "extra", None) or {}
    if not isinstance(extra, dict):
        return "", -1
    path_name = (extra.get("volume_boss_path_rank") or "").strip()
    if not path_name or not registry:
        return "", -1
    key = resolve_realm_in_registry(path_name, registry) or path_name
    meta = registry.get(key) or {}
    if meta.get("axis") != "path":
        return path_name, -1
    rank = meta.get("rank")
    if isinstance(rank, int):
        return path_name, rank
    try:
        return path_name, int(rank)
    except (TypeError, ValueError):
        return path_name, -1


def format_volume_realm_fix_hint(issues: list[dict]) -> str:
    """将卷级境界校验问题格式化为定向修正提示（供 gen_volumes 重试注入）。"""
    realm_issues = [
        i for i in issues
        if i.get("type") in ("villain_alignment", "realm_mismatch", "path_alignment")
        and i.get("severity") == "high"
    ]
    if not realm_issues:
        return ""
    lines = ["\n【⚠️ 上次生成存在致命战力曲线错误，必须修正后重出】"]
    for item in realm_issues:
        lines.append(f"- {item.get('description', '')} → {item.get('suggestion', '')}")
    lines.append(
        "铁律：后卷 volume_boss_realm 的 rank 必须严格大于前卷；"
        "后卷 volume_boss_path_rank（道途）宜同步递增；"
        "当卷 BOSS 可以是新角色，但境界绝不能倒退。"
        "请逐卷核对 volume_boss / volume_boss_realm 后再输出 JSON。"
    )
    return "\n".join(lines) + "\n"


def build_volumes_gate_preview(
    db: Any,
    project_id: Any,
    ctx: dict,
) -> dict:
    """卷闸门审阅摘要：各卷 BOSS/境界 + 校验告警。"""
    from app.models import Character, OutlineNode

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    chars = db.query(Character).filter(Character.project_id == project_id).all()
    protagonist = (ctx.get("protagonist") or "").strip()
    level_names: list[str] = list(ctx.get("power_level_names") or [])
    rank_map = _build_realm_rank_map(level_names)

    preview_rows: list[dict] = []
    for vol in volumes:
        extra = vol.extra or {}
        boss = (extra.get("volume_boss") or "").strip()
        realm = (extra.get("volume_boss_realm") or "").strip()
        if not boss or not realm:
            inferred_name, inferred_rank = _volume_peak_threat(
                vol, chars, protagonist, level_names, rank_map,
            )
            if not boss:
                boss = inferred_name
            if not realm and inferred_rank >= 0 and level_names:
                realm = level_names[inferred_rank]
        preview_rows.append({
            "sort_order": vol.sort_order,
            "title": vol.title or "",
            "phase": vol.phase or "",
            "volume_boss": boss or None,
            "volume_boss_realm": realm or None,
            "volume_boss_path": (extra.get("volume_boss_path") or "").strip() or None,
            "volume_boss_path_rank": (extra.get("volume_boss_path_rank") or "").strip() or None,
            "planned_chapters": (extra or {}).get("planned_chapters"),
        })

    lint_issues = lint_volume_entity_issues(db, project_id, ctx)
    high_realm = [
        i for i in lint_issues
        if i.get("severity") == "high"
        and i.get("type") in ("villain_alignment", "realm_mismatch")
    ]

    return {
        "volumes_count": len(volumes),
        "volumes_preview": preview_rows,
        "volume_lint_issues": lint_issues,
        "volume_realm_warnings": high_realm,
        "has_realm_warnings": bool(high_realm),
    }


def _extract_orgs(text: str, faction_names: list[str] | None = None) -> set[str]:
    """从叙述文本中提取组织名（每个后缀位置取最长 canonical 或最长非登记名）。"""
    if not text:
        return set()
    found: set[str] = set()
    canon = faction_names or []
    for i, ch in enumerate(text):
        if ch not in _ORG_SUFFIX_CHARS:
            continue
        cands: list[str] = []
        for length in range(1, 7):
            start = i - length
            if start < 0:
                continue
            prefix = text[start:i]
            if not prefix or not all("\u4e00" <= c <= "\u9fff" for c in prefix):
                continue
            if _ORG_BAD_PREFIX_RE.match(prefix):
                continue
            cands.append(prefix + ch)
        if not cands:
            continue
        matched = [c for c in cands if _org_matches_canonical(c, canon)]
        if matched:
            found.add(max(matched, key=len))
        else:
            found.add(max(cands, key=len))
    return found


def _org_matches_canonical(org: str, faction_names: list[str]) -> bool:
    org = org.strip()
    if not org:
        return True
    for fn in faction_names:
        if org == fn or org in fn or fn in org:
            return True
        if SequenceMatcher(None, org, fn).ratio() >= 0.55:
            return True
    return False


def _extract_realm_near_name(text: str, name: str, level_names: list[str]) -> str | None:
    idx = text.find(name)
    if idx < 0:
        return None
    window = text[max(0, idx - 8) : idx + 36]
    for ln in sorted(level_names, key=len, reverse=True):
        if ln and ln in window:
            return ln
    m = _REALM_NEAR_NAME_RE.search(window)
    if m:
        cand = (m.group(1) or m.group(2) or "").strip()
        for ln in level_names:
            if ln in cand or cand in ln:
                return ln
    return None


def lint_volume_entity_issues(
    db: Any,
    project_id: Any,
    ctx: dict,
) -> list[dict]:
    """卷级实体交叉核验（不调用 LLM）。返回 consistency_issues 形态的 dict 列表。"""
    from app.models import Character, OutlineNode, PowerSystem

    issues: list[dict] = []
    from app.models import Faction

    faction_names: list[str] = list(ctx.get("faction_names") or [])
    if not faction_names:
        faction_names = [
            f.name
            for f in db.query(Faction).filter(Faction.project_id == project_id).all()
            if f.name
        ]

    level_names: list[str] = list(ctx.get("power_level_names") or [])
    if not level_names:
        ps = (
            db.query(PowerSystem)
            .filter(PowerSystem.project_id == project_id)
            .order_by(PowerSystem.sort_order)
            .first()
        )
        if ps and ps.levels:
            level_names = [
                lv.get("name", "")
                for lv in ps.levels
                if isinstance(lv, dict) and lv.get("name")
            ]

    rank_map = _build_realm_rank_map(level_names)
    max_rank = len(level_names) - 1 if level_names else -1

    volumes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.node_type == "volume",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if not volumes:
        return issues

    # ── 1. 卷文本中的组织名是否在势力登记表内 ─────────────────────────────
    orphan_orgs: set[str] = set()
    for vol in volumes:
        blob = " ".join(
            filter(None, [vol.title, vol.summary, vol.conflict, vol.hook])
        )
        for org in _extract_orgs(blob, faction_names):
            if not _org_matches_canonical(org, faction_names):
                orphan_orgs.add(org)

    for org in sorted(orphan_orgs):
        issues.append({
            "severity": "high",
            "type": "faction_mismatch",
            "description": f"卷骨架出现未登记势力「{org}」",
            "suggestion": f"将卷描述中的「{org}」统一改为势力档案中的 canonical 名称",
            "auto_detected": True,
        })

    # ── 2. 主角姓氏 vs 家族势力名 ───────────────────────────────────────────
    protagonist = (ctx.get("protagonist") or "").strip()
    protag_char = None
    if protagonist:
        protag_char = (
            db.query(Character)
            .filter(Character.project_id == project_id, Character.name == protagonist)
            .first()
        )
    protag_faction = (protag_char.faction or "").strip() if protag_char else _protagonist_faction_from_ctx(ctx)
    if protagonist and protag_faction and "家" in protag_faction:
        surname = protagonist[0]
        if surname and surname not in protag_faction:
            issues.append({
                "severity": "medium",
                "type": "faction_mismatch",
                "description": (
                    f"主角「{protagonist}」姓{surname}与势力「{protag_faction}」姓氏不一致"
                ),
                "suggestion": (
                    f"将主角 faction 改为与姓氏匹配之家族，或在背景中注明养子/外姓传承"
                ),
                "auto_detected": True,
            })

    # ── 3. 卷级 BOSS 境界曲线：后期卷 ≤ 前期卷 → 战力崩塌 ─────────────────
    protagonist = (ctx.get("protagonist") or "").strip()
    all_chars = (
        db.query(Character)
        .filter(Character.project_id == project_id)
        .all()
    )
    if rank_map and level_names:
        peak_by_vol: list[tuple[int, str, int, str]] = []  # (sort_order, name, rank, realm)
        for vol in volumes:
            peak_name, peak_rank = _volume_peak_threat(
                vol, all_chars, protagonist, level_names, rank_map,
            )
            if peak_rank >= 0:
                realm_label = level_names[peak_rank] if peak_rank < len(level_names) else ""
                peak_by_vol.append((vol.sort_order, peak_name, peak_rank, realm_label))

        for i in range(1, len(peak_by_vol)):
            prev_idx, prev_nm, prev_r, prev_realm = peak_by_vol[i - 1]
            cur_idx, cur_nm, cur_r, cur_realm = peak_by_vol[i]
            if cur_r <= prev_r:
                prev_label = prev_realm or (level_names[prev_r] if prev_r < len(level_names) else "")
                cur_label = cur_realm or (level_names[cur_r] if cur_r < len(level_names) else "")
                issues.append({
                    "severity": "high",
                    "type": "villain_alignment",
                    "description": (
                        f"第{cur_idx + 1}卷核心对立面「{cur_nm}」（{cur_label}，rank={cur_r}）"
                        f"境界不高于第{prev_idx + 1}卷「{prev_nm}」（{prev_label}，rank={prev_r}）"
                    ),
                    "suggestion": (
                        f"将第{cur_idx + 1}卷 volume_boss「{cur_nm}」的 volume_boss_realm "
                        f"提升至「{level_names[min(prev_r + 1, max_rank)]}」或以上"
                        if level_names and max_rank >= 0
                        else f"提升「{cur_nm}」境界至高于前期卷 BOSS"
                    ),
                    "auto_detected": True,
                })

    # ── 3b. 道途阶曲线：后期卷 BOSS path rank ≤ 前期卷 ─────────────────────
    registry: dict = dict(ctx.get("power_level_registry") or {})
    path_peak_by_vol: list[tuple[int, str, int, str]] = []
    for vol in volumes:
        path_nm, path_r = _volume_boss_path_rank(vol, registry)
        if path_r >= 0:
            path_peak_by_vol.append((vol.sort_order, path_nm, path_r, path_nm))

    for i in range(1, len(path_peak_by_vol)):
        prev_idx, prev_nm, prev_r, _ = path_peak_by_vol[i - 1]
        cur_idx, cur_nm, cur_r, cur_label = path_peak_by_vol[i]
        if cur_r <= prev_r:
            issues.append({
                "severity": "high",
                "type": "path_alignment",
                "description": (
                    f"第{cur_idx + 1}卷 BOSS 道途「{cur_label}」（rank={cur_r}）"
                    f"不高于第{prev_idx + 1}卷「{prev_nm}」（rank={prev_r}）"
                ),
                "suggestion": f"提升第{cur_idx + 1}卷 volume_boss_path_rank 至高于前期卷道途阶",
                "auto_detected": True,
            })

    # ── 4. 终局卷 Boss 境界低于体系顶档 ─────────────────────────────────────
    if max_rank >= 0 and level_names:
        top_name = level_names[-1]
        late_vols = [v for v in volumes if (v.phase or "") in ("climax", "ending")]
        for vol in late_vols or volumes[-1:]:
            blob = " ".join(
                filter(None, [vol.title, vol.summary, vol.conflict, vol.hook])
            )
            if not _BOSS_HINT_RE.search(blob):
                continue
            mentioned_ranks = [
                rank_map[ln]
                for ln in level_names
                if ln in blob and ln in rank_map
            ]
            if mentioned_ranks and max(mentioned_ranks) < max_rank - 1:
                low = level_names[max(mentioned_ranks)]
                issues.append({
                    "severity": "high",
                    "type": "realm_mismatch",
                    "description": (
                        f"终局卷「{vol.title}」Boss 境界「{low}」低于体系最高「{top_name}」"
                    ),
                    "suggestion": f"将终局 Boss 境界提升至「{top_name}」或次高档",
                    "auto_detected": True,
                })
                break

    return issues
