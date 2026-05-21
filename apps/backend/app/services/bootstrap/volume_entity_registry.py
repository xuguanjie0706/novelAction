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

_ORG_SUFFIX_CHARS = frozenset("宗殿堂府家门阁派盟宫国城谷岛会帮")
# 组织名前缀不应以叙事动词/介词开头（避免「拜入云霄剑宗」整段被吞）
_ORG_BAD_PREFIX_RE = re.compile(
    r"^[与攻拜入归投赴袭灭屠诸各其于在从向对和及]"
)

# 卷末/终局 Boss 常见称谓片段
_BOSS_HINT_RE = re.compile(r"(?:冥皇|魔尊|天帝|仙帝|至尊|主宰|大魔|终极|最终)")

_REALM_NEAR_NAME_RE = re.compile(
    r"[\(（]([^）\)]{2,8})[\)）]|"
    r"(?:为|达|至|已是|突破至|晋入)\s*([\u4e00-\u9fff]{2,8})"
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
                "  ⚠️ 反派境界曲线：越靠后的卷，当卷核心反派 effective 境界 rank 须 ≥ 前期卷核心反派；"
                "终局 Boss 须达到或逼近境界体系最高档（见下）。"
            )

    if level_names:
        top = level_names[-1]
        lines.append(f"【境界阶梯（低→高）】{' → '.join(level_names)}")
        lines.append(
            f"  ⚠️ 全书终局对立面（冥皇/魔尊等）须处于最高档「{top}」或次高档，"
            f"禁止终局 Boss 仅停留在中阶境界。"
        )

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

    # ── 3. 卷内提及反派境界：后期卷 ≤ 前期卷 → 战力崩塌 ───────────────────
    antagonists = (
        db.query(Character)
        .filter(Character.project_id == project_id, Character.role == "antagonist")
        .all()
    )
    antag_names = [c.name for c in antagonists if c.name]
    if antag_names and rank_map:
        peak_by_vol: list[tuple[int, str, int]] = []  # (vol_idx, name, rank)
        for vol in volumes:
            blob = " ".join(
                filter(None, [vol.title, vol.summary, vol.conflict, vol.hook])
            )
            vol_peak = -1
            vol_peak_name = ""
            for nm in antag_names:
                if nm not in blob:
                    continue
                realm = _extract_realm_near_name(blob, nm, level_names)
                r = rank_map.get(realm or "", -1)
                if r < 0 and antagonists:
                    ch = next((c for c in antagonists if c.name == nm), None)
                    if ch:
                        r = (
                            ch.realm_rank
                            if ch.realm_rank is not None
                            else rank_map.get(ch.current_realm or "", -1)
                        )
                if r > vol_peak:
                    vol_peak, vol_peak_name = r, nm
            if vol_peak >= 0:
                peak_by_vol.append((vol.sort_order, vol_peak_name, vol_peak))

        for i in range(1, len(peak_by_vol)):
            prev_idx, prev_nm, prev_r = peak_by_vol[i - 1]
            cur_idx, cur_nm, cur_r = peak_by_vol[i]
            if cur_r <= prev_r:
                issues.append({
                    "severity": "high",
                    "type": "villain_alignment",
                    "description": (
                        f"第{cur_idx + 1}卷反派「{cur_nm}」境界(rank={cur_r})"
                        f"不高于第{prev_idx + 1}卷「{prev_nm}」(rank={prev_r})"
                    ),
                    "suggestion": (
                        f"将「{cur_nm}」境界提升至「{level_names[min(prev_r + 1, max_rank)]}」或以上"
                        if level_names and max_rank >= 0
                        else f"提升「{cur_nm}」境界至高于前期反派"
                    ),
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
