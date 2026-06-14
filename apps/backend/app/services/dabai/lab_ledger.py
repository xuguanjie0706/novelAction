"""dabai 实验书架双台账 — 资产（功法/道具/金手指）+ 人物关系。

三个职责：
  1. seed：从 golden_finger / characters 派生开局台账（幂等，source=seed）；
  2. 注入：写章与导演单 prompt 的「当前台账」块（防能力/装备/关系漂移）；
  3. 维护：复盘提取的 asset_changes / relation_changes 落账（去重幂等）。

v2（2026-06）新增：
  - 资产品阶/数值字段（grade/base_stat/cooldown_chapters/last_used_chapter）
  - build_panel_snapshot：供复盘结束后生成系统面板快照（数值绝对基准）
  - 注入块展示技能冷却状态（冷却中不可使用的技能明确标红）

与精品文 Skill/Item/CharacterRelationship 完全隔离，不维护平行栈。
"""
from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiAsset, DabaiMemory, DabaiPanelSnapshot, DabaiRelation
from app.services.dabai.lab_ledger_seed import seed_ledgers

logger = logging.getLogger(__name__)

_ASSET_KINDS = {"skill", "item", "golden_finger"}
_KIND_LABELS = {"skill": "功法技能", "item": "道具法宝", "golden_finger": "金手指"}
_ROLE_ATTITUDE = {
    "打脸对象": "敌对",
    "反派": "敌对",
    "女主": "暧昧",
    "导师": "扶持",
}

# 系统 UI 计数，非可注入资产（复盘误提取时过滤）
_ASSET_NOISE_NAMES = frozenset({"修为点", "修为", "经验点", "熟练度", "属性点"})
_ASSET_NOISE_RE = re.compile(r"^修为点\d*$")

_REALM_RE = re.compile(
    r"(淬体|气海|灵纹|神宫|王座|涅槃|至尊|神吞)(?:境)?([一二三四五六七八九十]+|\d+)重",
)

# 品阶数字 → 汉字标签（grade 字段）
_GRADE_LABELS = {0: "凡品", 1: "灵品", 2: "仙品", 3: "神品", 4: "传说"}
_GRADE_KEYWORDS = {
    "凡": 0, "下品": 0, "灵": 1, "中品": 1, "仙": 2, "上品": 2,
    "神": 3, "极品": 3, "传说": 4, "天外": 4,
}


def _guess_grade(name: str, description: str) -> int | None:
    """从名称/描述关键词猜测品阶；猜不出返回 None。"""
    text = (name or "") + (description or "")
    for kw, grade in _GRADE_KEYWORDS.items():
        if kw in text:
            return grade
    return None


def _is_noise_asset(name: str) -> bool:
    """系统内部计数/面板词，不应进入资产台账。"""
    n = name.strip()
    if not n:
        return True
    if n in _ASSET_NOISE_NAMES or _ASSET_NOISE_RE.match(n):
        return True
    return False


def _parse_sub_realm_label(text: str) -> str | None:
    """从文本取最后一次「大境+重数」表述，如 淬体境六重。"""
    matches = _REALM_RE.findall(text or "")
    if not matches:
        return None
    major, sub = matches[-1]
    return f"{major}境{sub}重"


def _major_to_rank(project: DabaiProject, major: str) -> int | None:
    """大境名 → power_ladder.rank（档位数）。"""
    for lvl in (project.power_ladder or {}).get("levels") or []:
        name = str(lvl.get("name") or "")
        if major in name or name.startswith(major):
            try:
                return int(lvl.get("rank") or 0) or None
            except (TypeError, ValueError):
                return None
    return None


def _roster_names(project: DabaiProject) -> set[str]:
    return {c.name for c in project.characters if c.name}


def _appeared_character_names(
    db: Session, project: DabaiProject, up_to_chapter: int,
) -> set[str]:
    """截至某章，在正文或记忆 tags 中出现过的人名（用于排除幽灵种子关系）。"""
    roster = _roster_names(project)
    if not roster or up_to_chapter < 1:
        return set()
    appeared: set[str] = set()
    rows = (
        db.query(DabaiChapterOutline.content)
        .filter(
            DabaiChapterOutline.project_id == project.id,
            DabaiChapterOutline.chapter_number <= up_to_chapter,
            DabaiChapterOutline.content.isnot(None),
        )
        .all()
    )
    for (content,) in rows:
        text = content or ""
        for name in roster:
            if name in text:
                appeared.add(name)
    for (tags,) in (
        db.query(DabaiMemory.tags)
        .filter(
            DabaiMemory.project_id == project.id,
            DabaiMemory.chapter_number <= up_to_chapter,
        )
        .all()
    ):
        for tag in tags or []:
            if tag in roster:
                appeared.add(tag)
    return appeared


def _relation_visible(
    rel: DabaiRelation, appeared: set[str], on_stage: set[str],
) -> bool:
    """种子关系仅在人物已出镜或本章在场时注入，避免林梦瑶类幽灵关系污染。"""
    if rel.to_name in on_stage:
        return True
    if (rel.last_change_chapter or 0) > 0:
        return True
    if rel.source != "seed":
        return True
    return rel.to_name in appeared


def protagonist_name(project: DabaiProject) -> str:
    """主角名：role 含「主角」者优先，否则第一个人物，兜底「主角」。"""
    for c in project.characters:
        if "主角" in (c.role or ""):
            return c.name
    return project.characters[0].name if project.characters else "主角"


# ── 注入块 ───────────────────────────────────────────────────────────────────
def build_ledger_block(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
) -> str:
    """写章/导演单注入块：主角当前资产 + 在场人物关系 + 硬约束。空台账返回空串。"""
    protag = protagonist_name(project)
    lines: list[str] = []

    meta = project.meta or {}
    realm = meta.get("protagonist_realm")
    realm_ch = meta.get("protagonist_realm_chapter")
    if realm:
        suffix = f"（第{realm_ch}章末确立）" if realm_ch else ""
        lines.append(f"- {protag}当前境界：{realm}{suffix}")

    cur_chapter = ch.chapter_number or 1
    assets = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == project.id, DabaiAsset.status == "active")
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .limit(20).all()
    )
    by_kind: dict[str, list[str]] = {}
    cooldown_lines: list[str] = []
    others: list[str] = []
    for a in assets:
        grade_tag = f"[{_GRADE_LABELS[a.grade]}]" if a.grade is not None else ""
        desc_short = f"（{(a.description or '')[:20]}）" if a.description else ""
        label = f"{a.name}{grade_tag}{desc_short}"
        if (a.owner or protag) == protag:
            # 技能冷却检测
            if a.kind == "skill" and (a.cooldown_chapters or 0) > 0:
                last = a.last_used_chapter or 0
                remaining = (last + (a.cooldown_chapters or 0)) - cur_chapter
                if remaining > 0:
                    cooldown_lines.append(f"{a.name}（冷却中，还需{remaining}章）")
                    continue  # 冷却中的技能不放入可用列表
            by_kind.setdefault(a.kind or "item", []).append(label)
        else:
            others.append(
                f"{a.owner}的{a.name}（{_KIND_LABELS.get(a.kind or 'item', '道具')}{desc_short}）",
            )
    for kind in ("golden_finger", "skill", "item"):
        if by_kind.get(kind):
            lines.append(f"- {protag}的{_KIND_LABELS[kind]}：{'、'.join(by_kind[kind][:8])}")
    if cooldown_lines:
        lines.append(f"- ⛔冷却中（本章禁止使用）：{'、'.join(cooldown_lines)}")
    if others:
        lines.append(f"- 其他人物持有（不归{protag}使用）：{'；'.join(others[:6])}")

    on_stage = {str(n) for n in (ch.witnesses or [])} | {
        str(n) for n in (ch.involved_characters or [])
    }
    upto = ch.chapter_number or 1
    if (ch.status or "planned") == "planned" and not (ch.content or "").strip():
        upto = max(0, upto - 1)
    appeared = _appeared_character_names(db, project, upto)
    rels = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == project.id, DabaiRelation.from_name == protag)
        .all()
    )
    rel_lines = [
        f"{r.to_name}：{r.attitude or '中立'}"
        + (f"（第{r.last_change_chapter}章起）" if r.last_change_chapter else "")
        for r in rels
        if _relation_visible(r, appeared, on_stage)
        and (not on_stage or r.to_name in on_stage)
    ]
    if rel_lines:
        lines.append(f"- 在场人物对{protag}的关系：{'；'.join(rel_lines[:10])}")

    # 已锁定的技能/道具详细规格（用法/代价/进阶/限制）——后续章节沿用，
    # 经此块透传给分场/正文/导演单，保证全书用法一致（delegation 防循环导入）。
    from app.services.dabai.lab_asset_spec import build_locked_spec_block
    spec_block = build_locked_spec_block(db, project, ch)

    if not lines and not spec_block:
        return ""
    if lines:
        lines.append(
            "- ★硬约束：禁止使用台账之外未获得的功法/法宝；已消耗/遗失的不得再用；"
            "人物态度须与台账一致，态度变化必须在正文交代原因。"
        )
    block = "【当前台账（既定事实，不可违背）】\n" + "\n".join(lines) if lines else ""
    if spec_block:
        block = f"{block}\n\n{spec_block}" if block else spec_block
    return block


# ── 复盘落账 ─────────────────────────────────────────────────────────────────
def _apply_asset_change(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
    item: dict, protag: str,
) -> str | None:
    action = str(item.get("action") or "").lower()
    name = str(item.get("name") or "").strip()[:120]
    if not name or _is_noise_asset(name):
        return None
    if action not in ("gain", "use", "consume", "lose", "upgrade"):
        return None
    kind = str(item.get("kind") or "item").lower()
    if kind == "golden_finger":
        gf_name = str((project.golden_finger or {}).get("name") or "").strip()
        if gf_name and name != gf_name:
            return None
    owner = str(item.get("owner") or protag).strip()[:100]
    note = str(item.get("note") or "")[:300]
    row = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == project.id,
                DabaiAsset.name == name, DabaiAsset.owner == owner)
        .first()
    )
    raw_grade = item.get("grade")
    new_grade: int | None = None
    try:
        new_grade = int(raw_grade) if raw_grade is not None else None
        if new_grade is not None and not 0 <= new_grade <= 4:
            new_grade = None
    except (TypeError, ValueError):
        new_grade = None
    if new_grade is None:
        new_grade = _guess_grade(name, note)

    raw_stat = item.get("base_stat")
    base_stat: dict | None = raw_stat if isinstance(raw_stat, dict) else None

    raw_cd = item.get("cooldown_chapters")
    cooldown: int | None = None
    try:
        cooldown = int(raw_cd) if raw_cd is not None else None
    except (TypeError, ValueError):
        pass

    if action == "gain":
        if row:
            if row.status != "active":  # 失而复得
                row.status, row.status_chapter = "active", ch.chapter_number
                # 数值字段顺带补全（原先 seed 时可能为空）
                if new_grade is not None and row.grade is None:
                    row.grade = new_grade
                return f"复得：{name}"
            return None  # 已持有，去重
        db.add(DabaiAsset(
            project_id=project.id,
            kind=kind if kind in _ASSET_KINDS else "item",
            name=name, owner=owner, description=note,
            acquired_chapter=ch.chapter_number, status="active", source="debrief",
            grade=new_grade, base_stat=base_stat, cooldown_chapters=cooldown,
        ))
        return f"新获：{name}"
    if action == "use":
        # 技能本章被施展：更新 last_used_chapter，冷却计时从本章起算
        # 技能本身仍 active，不消耗；消耗品请用 consume
        if row and row.status == "active" and row.kind == "skill":
            row.last_used_chapter = ch.chapter_number
            # 若 AI 顺带给了 cooldown_chapters，顺手更新（允许复盘修正冷却设定）
            if cooldown is not None and row.cooldown_chapters is None:
                row.cooldown_chapters = cooldown
            return f"使用：{name}（冷却计时第{ch.chapter_number}章起）"
        return None  # 非技能或不存在，忽略
    if not row:
        return None
    if action == "upgrade":
        row.description = note or row.description
        row.status_chapter = ch.chapter_number
        row.enhancement_level = (row.enhancement_level or 0) + 1
        if new_grade is not None and new_grade > (row.grade or 0):
            row.grade = new_grade  # 升阶后品阶可能提升
        if base_stat:
            row.base_stat = base_stat
        return f"升级：{name}（+{row.enhancement_level}阶）"
    row.status = "consumed" if action == "consume" else "lost"
    row.status_chapter = ch.chapter_number
    return f"{'消耗' if action == 'consume' else '遗失'}：{name}"


def _apply_relation_change(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline,
    item: dict, protag: str,
) -> str | None:
    to_name = str(item.get("to") or "").strip()[:100]
    attitude = str(item.get("attitude") or "").strip()[:40]
    if not to_name or not attitude:
        return None
    from_name = str(item.get("from") or protag).strip()[:100]
    reason = str(item.get("reason") or "")[:120]
    row = (
        db.query(DabaiRelation)
        .filter(DabaiRelation.project_id == project.id,
                DabaiRelation.from_name == from_name,
                DabaiRelation.to_name == to_name)
        .first()
    )
    entry = {"chapter": ch.chapter_number, "attitude": attitude, "reason": reason}
    if row:
        if row.attitude == attitude and row.last_change_chapter == ch.chapter_number:
            return None  # 同章重跑去重
        history = list(row.history or [])
        # 同章重跑但态度修正：替换该章旧记录
        history = [h for h in history if h.get("chapter") != ch.chapter_number]
        history.append(entry)
        old = row.attitude or "中立"
        row.attitude, row.history = attitude, history
        row.last_change_chapter = ch.chapter_number
        return f"{to_name}：{old}→{attitude}"
    db.add(DabaiRelation(
        project_id=project.id, from_name=from_name, to_name=to_name,
        attitude=attitude, note=reason, last_change_chapter=ch.chapter_number,
        history=[entry], source="debrief",
    ))
    return f"{to_name}：新增（{attitude}）"


def apply_ledger_changes(
    db: Session, project: DabaiProject, ch: DabaiChapterOutline, result: dict,
) -> tuple[list[str], list[str]]:
    """复盘结果中的台账变更落库；返回 (资产变更摘要, 关系变更摘要)。不 commit。"""
    protag = protagonist_name(project)
    asset_logs: list[str] = []
    for item in list(result.get("asset_changes") or [])[:8]:
        if isinstance(item, dict):
            log = _apply_asset_change(db, project, ch, item, protag)
            if log:
                asset_logs.append(log)
    relation_logs: list[str] = []
    for item in list(result.get("relation_changes") or [])[:8]:
        if isinstance(item, dict):
            log = _apply_relation_change(db, project, ch, item, protag)
            if log:
                relation_logs.append(log)
    return asset_logs, relation_logs


def mark_skill_used(
    db: Session, project: DabaiProject, skill_name: str, chapter_number: int,
) -> None:
    """写章时标记某技能已被使用（更新 last_used_chapter）。不 commit。

    由写章 post-hook 调用，确保冷却逻辑在下章正确生效。
    skill_name 匹配宽松（contains）。
    """
    rows = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.kind == "skill",
            DabaiAsset.status == "active",
            DabaiAsset.name.contains(skill_name[:30]),
        )
        .all()
    )
    for row in rows:
        row.last_used_chapter = chapter_number


def build_panel_snapshot(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    realm_info: dict | None = None,
) -> DabaiPanelSnapshot:
    """构建并持久化系统面板快照（不 commit）。

    Args:
        realm_info: 复盘输出的境界快照，结构 {realm, sub_level, max_sub, combat_power}。
                    可为 None（将从 project.meta 取境界标签兜底）。
    Returns:
        未 commit 的 DabaiPanelSnapshot 实例（已 add 到 session）。
    """
    protag = protagonist_name(project)
    cur_chapter = ch.chapter_number or 1

    # ── 境界信息 ─────────────────────────────────────────────────────────────
    meta = project.meta or {}
    realm_str = str(meta.get("protagonist_realm") or "")
    sub_level: int | None = None
    max_sub: int | None = None
    combat_power: int | None = None
    if realm_info:
        realm_str = str(realm_info.get("realm") or realm_str)
        try:
            sub_level = int(realm_info["sub_level"]) if realm_info.get("sub_level") else None
            max_sub = int(realm_info["max_sub"]) if realm_info.get("max_sub") else None
            combat_power = int(realm_info["combat_power"]) if realm_info.get("combat_power") else None
        except (TypeError, ValueError):
            pass

    # ── 资产分类 ─────────────────────────────────────────────────────────────
    assets = (
        db.query(DabaiAsset)
        .filter(DabaiAsset.project_id == project.id,
                DabaiAsset.status == "active",
                DabaiAsset.owner == protag)
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .limit(30).all()
    )
    skills, items, golden_fingers = [], [], []
    for a in assets:
        grade_label = _GRADE_LABELS.get(a.grade) if a.grade is not None else None
        entry: dict = {
            "name": a.name,
            "grade": a.grade,
            "grade_label": grade_label,
            "description": (a.description or "")[:100],
        }
        if a.kind == "skill":
            last = a.last_used_chapter or 0
            cd = a.cooldown_chapters or 0
            remaining = max(0, (last + cd) - cur_chapter) if cd > 0 else 0
            entry.update({
                "cooldown_chapters": cd,
                "last_used_chapter": last,
                "on_cooldown": remaining > 0,
                "cooldown_remaining": remaining,
                "enhancement_level": a.enhancement_level or 0,
            })
            if a.base_stat:
                entry["base_stat"] = a.base_stat
            skills.append(entry)
        elif a.kind == "item":
            if a.base_stat:
                entry["base_stat"] = a.base_stat
            entry["enhancement_level"] = a.enhancement_level or 0
            items.append(entry)
        else:  # golden_finger
            golden_fingers.append(entry)

    # 章末位置：复盘提取的下一章开笔位置基准（空间防漂移；可为空）
    location = str((realm_info or {}).get("location") or "").strip()[:50]

    snap = DabaiPanelSnapshot(
        project_id=project.id,
        chapter_id=ch.id,
        chapter_number=cur_chapter,
        snapshot={
            "realm": realm_str,
            "sub_level": sub_level,
            "max_sub": max_sub,
            "combat_power": combat_power,
            "location": location,
            "skills": skills,
            "items": items,
            "golden_fingers": golden_fingers,
        },
    )
    db.add(snap)
    return snap


def prune_noise_assets(db: Session, project: DabaiProject) -> int:
    """删除误落的系统计数类资产行；返回删除条数。不 commit。"""
    removed = 0
    for row in db.query(DabaiAsset).filter(DabaiAsset.project_id == project.id).all():
        if _is_noise_asset(row.name or ""):
            db.delete(row)
            removed += 1
    return removed


def sync_protagonist_realm(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    *,
    memories: list | None = None,
) -> str | None:
    """复盘后同步主角境界：meta.protagonist_realm + 章纲 realm_rank（档位数单调不减）。

    Args:
        memories: 刚落库的本章记忆行，优先读 state 类型。
    Returns:
        解析到的境界标签（如 淬体境六重），未解析则 None。
    """
    content = re.sub(r"<[^>]+>", "", ch.content or "").strip()
    label = _parse_sub_realm_label(content[-2500:] if content else "")
    if memories:
        for mem in reversed(memories):
            if getattr(mem, "mem_type", None) != "state":
                continue
            text = getattr(mem, "content", "") or ""
            if "境" not in text and "重" not in text:
                continue
            parsed = _parse_sub_realm_label(text)
            if parsed:
                label = parsed
                break
    if not label:
        return None

    meta = dict(project.meta or {})
    meta["protagonist_realm"] = label
    meta["protagonist_realm_chapter"] = ch.chapter_number
    project.meta = meta

    m = _REALM_RE.search(label)
    if m:
        new_rank = _major_to_rank(project, m.group(1))
        if new_rank and (ch.realm_rank is None or new_rank >= int(ch.realm_rank)):
            ch.realm_rank = new_rank
    return label
