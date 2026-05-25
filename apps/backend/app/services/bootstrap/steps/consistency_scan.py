"""Bootstrap Step 14：全局一致性扫描。

两阶段检验
----------
1. 纯代码预检（_structural_precheck）：
   - 死亡/失踪人物仍出现在章纲 involved_character_ids
   - 技能 level_required 高于掌握者当前 realm_rank
   - 道具 first_appearance_chapter 与章纲里的 power_milestone/core_event 不一致
   - 连续卷之间 sort_order 跳号（卷间时序缺口）
   预检结果作为 high-severity 硬伤直接写入 issues，无需 AI。

2. AI 叙事层分析（同旧版5条检查 + 新增1条反派行动时间线对齐）：
   接收预检发现的摘要作为上下文，补充结构代码检不到的语义矛盾。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json

logger = logging.getLogger(__name__)


# ── 阶段一：纯代码预检 ────────────────────────────────────────────────────────

def _structural_precheck(svc: Any, project, ctx: dict) -> list[dict]:
    """纯代码结构性预检，不调用 AI，返回可直接合并到 issues 的 dict 列表。"""
    from app.models import Character, Item, OutlineNode, Skill
    from app.services.bootstrap.power_registry import resolve_realm_in_registry

    issues: list[dict] = []
    db = svc.db
    pid = project.id

    # 1. 死亡/失踪人物仍出现在章纲 ──────────────────────────────────────────
    dead_chars = {
        str(c.id): c.name
        for c in db.query(Character)
        .filter(
            Character.project_id == pid,
            Character.current_status.in_(["dead", "missing", "sealed"]),
        )
        .all()
    }
    if dead_chars:
        chapter_plans = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.project_id == pid,
                OutlineNode.node_type == "chapter_plan",
            )
            .all()
        )
        for node in chapter_plans:
            ids = node.involved_character_ids or []
            for cid in ids:
                cid_str = str(cid)
                if cid_str in dead_chars:
                    issues.append({
                        "severity": "high",
                        "type": "character_status_conflict",
                        "description": (
                            f"「{dead_chars[cid_str]}」状态为死亡/失踪，"
                            f"却出现在章纲第{node.sort_order + 1}章"
                        ),
                        "suggestion": f"确认「{dead_chars[cid_str]}」是否应在该章出场",
                        "auto_detected": True,
                    })

    # 2. 技能境界要求高于掌握者当前 realm_rank ────────────────────────────────
    chars_by_id = {
        str(c.id): c
        for c in db.query(Character).filter(Character.project_id == pid).all()
    }
    skills = (
        db.query(Skill)
        .filter(Skill.project_id == pid, Skill.level_required.isnot(None))
        .all()
    )
    power_level_names = ctx.get("power_level_names", [])
    level_rank_map = {name: i for i, name in enumerate(power_level_names)}
    registry = ctx.get("power_level_registry") or {}

    for skill in skills:
        req_name = (skill.level_required or "").strip()
        req_rank = None
        resolved = resolve_realm_in_registry(req_name, registry) if registry else None
        if resolved and resolved in registry:
            meta = registry[resolved]
            if meta.get("axis") == "primary" and isinstance(meta.get("rank"), int):
                req_rank = meta["rank"]
        if req_rank is None:
            req_rank = level_rank_map.get(resolved or req_name)
        if req_rank is None:
            continue
        for cid in (skill.mastered_by_character_ids or []):
            char = chars_by_id.get(str(cid))
            if not char:
                continue
            char_rank = char.realm_rank if char.realm_rank is not None else None
            if char_rank is None and registry:
                cr = resolve_realm_in_registry(char.current_realm, registry)
                if cr and cr in registry and registry[cr].get("axis") == "primary":
                    char_rank = registry[cr].get("rank")
            if char_rank is None:
                char_rank = level_rank_map.get(char.current_realm or "", None)
            if char_rank is not None and char_rank < req_rank:
                issues.append({
                    "severity": "medium",
                    "type": "skill_realm_conflict",
                    "description": (
                        f"「{char.name}」当前境界（rank={char_rank}）低于"
                        f"技能「{skill.name}」要求（{req_name}，rank={req_rank}）"
                    ),
                    "suggestion": f"推迟「{skill.name}」获得章节或调整境界设定",
                    "auto_detected": True,
                })

    # 3. 道具 first_appearance_chapter 与章纲章数不匹配 ──────────────────────
    total_ch1_plans = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == pid,
            OutlineNode.node_type == "chapter_plan",
        )
        .count()
    )
    if total_ch1_plans > 0:
        items = (
            db.query(Item)
            .filter(
                Item.project_id == pid,
                Item.first_appearance_chapter.isnot(None),
            )
            .all()
        )
        for item in items:
            fac = item.first_appearance_chapter
            if fac and fac <= total_ch1_plans:
                # 检查对应章节 power_milestone 或 summary 是否提到该道具
                target_node = (
                    db.query(OutlineNode)
                    .filter(
                        OutlineNode.project_id == pid,
                        OutlineNode.node_type == "chapter_plan",
                        OutlineNode.sort_order == fac - 1,
                    )
                    .first()
                )
                if target_node:
                    combined = " ".join(filter(None, [
                        target_node.summary or "",
                        target_node.power_milestone or "",
                        (target_node.extra or {}).get("core_event", ""),
                    ]))
                    if item.name not in combined:
                        issues.append({
                            "severity": "low",
                            "type": "item_appearance_gap",
                            "description": (
                                f"道具「{item.name}」设定首次出现于第{fac}章，"
                                f"但该章章纲未提及"
                            ),
                            "suggestion": f"在第{fac}章章纲中补充「{item.name}」登场描述",
                            "auto_detected": True,
                        })

    # 4. 卷 sort_order 跳号检查（卷间时序缺口）────────────────────────────────
    volumes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == pid, OutlineNode.node_type == "volume")
        .order_by(OutlineNode.sort_order)
        .all()
    )
    for i, vol in enumerate(volumes):
        if vol.sort_order != i:
            issues.append({
                "severity": "medium",
                "type": "volume_order_gap",
                "description": f"卷排序不连续：第{i}位卷的 sort_order={vol.sort_order}",
                "suggestion": "重新对卷节点 sort_order 做连续赋值",
                "auto_detected": True,
            })
            break  # 一条提示即可

    # 5. 卷级实体：势力别名 / 反派境界曲线 / 终局 Boss 档位 ─────────────────
    try:
        from app.services.bootstrap.volume_entity_registry import lint_volume_entity_issues

        issues.extend(lint_volume_entity_issues(db, pid, ctx))
    except Exception:
        logger.exception("consistency_scan 卷级实体预检跳过 project=%s", pid)

    return issues


# ── 阶段二：AI 叙事层分析 ─────────────────────────────────────────────────────

async def gen_consistency_scan(svc: Any, project, ctx: dict) -> list:
    """全局一致性扫描：代码预检 + AI 叙事层分析，结果合并写入 Project.extra。"""
    # ── 阶段一：纯代码预检 ────────────────────────────────────────────────
    try:
        precheck_issues = _structural_precheck(svc, project, ctx)
    except Exception:
        logger.exception("consistency_scan 代码预检异常，跳过（项目=%s）", project.id)
        precheck_issues = []

    # ── 阶段二：AI 分析 ───────────────────────────────────────────────────
    system = (
        "你是有30年经验的网络小说总编辑，专门做稿件前置审核。"
        "只返回 JSON 数组，不要任何解释文字。"
    )

    power_summary = ctx.get("power_summary", "（未设定）")
    faction_summary = ctx.get("faction_summary", "（未设定）")
    char_realms = ctx.get("char_realms", {})
    char_names = ctx.get("char_names", [])
    skill_names = ctx.get("skill_names", [])
    item_names = ctx.get("item_names", [])
    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    protagonist = ctx.get("protagonist", "主角")
    villain_arc_summary = ctx.get("villain_arc_summary", "")

    char_realm_lines = "\n".join(
        f"- {name}：境界={realm}" for name, realm in char_realms.items()
    )
    precheck_hint = ""
    if precheck_issues:
        precheck_hint = (
            "\n【代码预检已发现的硬伤（你无需重复，专注语义层矛盾）】\n"
            + "\n".join(f"  - {i['description']}" for i in precheck_issues)
            + "\n"
        )

    prompt = f"""小说：《{ctx.get('project_title', '未命名')}》（{ctx.get('genre', '')}）

【境界体系】
{power_summary}

【势力档案摘要】
{faction_summary}

【人物+当前境界】
{char_realm_lines or '（未设定）'}

【人物列表】{', '.join(char_names)}
主角：{protagonist}
主角起点境界：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}

【已生成技能】{', '.join(skill_names) or '（无）'}
【已生成道具】{', '.join(item_names) or '（无）'}

【故事线】
{storyline_summary}

【卷级骨架】
{volumes_summary}

【反派行动线摘要】
{villain_arc_summary or '（未设定）'}
{precheck_hint}
请对以上信息做「交叉核验」，找出所有显著矛盾或风险项，返回JSON数组：
[
  {{
    "severity": "high/medium/low",
    "type": "realm_mismatch/faction_mismatch/skill_requirement/storyline_gap/timeline_conflict/villain_alignment/other",
    "description": "具体矛盾描述（30字内）",
    "suggestion": "最简单的修复建议（20字内）"
  }}
]

检查重点（只查代码检不到的语义层）：
1. 人物卡 current_realm 是否在境界体系 levels 的合法名称里？
2. 主角和重要人物的 faction 是否与势力档案中势力名吻合（允许模糊匹配）？
3. 故事线类型与卷骨架冲突走向是否吻合？各故事线是否都能在卷骨架中找到推进节点？
4. 境界体系 protagonist_start_rank 与主角人物卡 current_realm 是否对应同一境界？
5. 反派行动线与卷骨架 phase 标记是否对齐（反派明显占优的卷是否标记了 dark_hour/turning）？
如果没有发现矛盾，返回空数组 []。只返回JSON数组，不要任何解释。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=2048, task="bootstrap.consistency_scan"
        )
        ai_issues = parse_json(raw)
        if not isinstance(ai_issues, list):
            ai_issues = []
    except Exception:
        ai_issues = []

    issues = precheck_issues + ai_issues

    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "consistency_issues": issues}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        pass

    return issues
