"""Bootstrap Step 14：全局一致性扫描。

两阶段检验
----------
1. 纯代码预检（_structural_precheck）：
   - 死亡/失踪人物仍出现在章纲 involved_character_ids
   - 技能 level_required 高于掌握者当前 realm_rank
   - 道具 first_appearance_chapter 与章纲里的 power_milestone/core_event 不一致
   - 连续卷之间 sort_order 跳号（卷间时序缺口）
   - 卷级结构化校验（volume_boss_realm 曲线、道途阶、终局 Boss 档位）
   以上有 ID/数值/结构化字段依据的项直接写入 issues。

   势力名后缀启发式（易误切叙事短语）**不**直写 issues，改由
   ``volume_faction_hints.collect_faction_semantic_hints`` 生成线索，交 AI 裁决。

2. AI 叙事层分析：
   交叉核验语义矛盾；势力/归属类以 AI 输出为准（可确认或驳回代码疑似线索）。
   最终 ``consistency_issues = 代码硬伤 + AI 确认项``。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)

# lint_volume_entity_issues 中可直写的类型（结构化字段 / 数值，非叙事启发式）
_VOLUME_LINT_HARD_TYPES = frozenset({
    "villain_alignment",
    "realm_mismatch",
    "path_alignment",
    "protagonist_alignment",
})


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

    # 5. 卷级实体：反派境界曲线 / 道途阶 / 终局 Boss（结构化字段，非势力后缀启发式）
    try:
        from app.services.bootstrap.volume_entity_registry import lint_volume_entity_issues

        vol_lint = lint_volume_entity_issues(db, pid, ctx)
        issues.extend(
            i for i in vol_lint if i.get("type") in _VOLUME_LINT_HARD_TYPES
        )
    except Exception:
        logger.exception("consistency_scan 卷级实体预检跳过 project=%s", pid)

    # 6. 开局承诺 ↔ roster：承诺击杀的目标若是后续卷 Boss → OC-LADDER 冲突
    #    （开局承诺与大纲必然矛盾的设计性根因，bootstrap 期即捕获）
    try:
        from app.services.bootstrap.opening_contract_consistency import (
            check_project_contract_consistency,
        )

        issues.extend(check_project_contract_consistency(project))
    except Exception:
        logger.exception("consistency_scan 承诺↔roster 预检跳过 project=%s", pid)

    return issues


# ── 阶段二：AI 叙事层分析 ─────────────────────────────────────────────────────

async def gen_consistency_scan(svc: Any, project, ctx: dict) -> list:
    """全局一致性扫描：代码硬伤 + 势力疑似线索交 AI 裁决，合并写入 Project.extra。"""
    # ── 阶段一：纯代码预检（硬伤直写）────────────────────────────────────────
    try:
        precheck_issues = _structural_precheck(svc, project, ctx)
    except Exception:
        logger.exception("consistency_scan 代码预检异常，跳过（项目=%s）", project.id)
        precheck_issues = []

    # 势力/归属疑似：仅作 AI 线索，不进入 precheck_issues
    faction_hints: list[str] = []
    try:
        from app.services.bootstrap.volume_faction_hints import collect_faction_semantic_hints

        faction_hints = collect_faction_semantic_hints(svc.db, project.id, ctx)
    except Exception:
        logger.exception("consistency_scan 势力疑似线索收集跳过 project=%s", project.id)

    # ── 阶段二：AI 分析（势力语义以 AI 输出为准）────────────────────────────
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
    ladder_summary = ctx.get("antagonist_ladder_summary") or ""
    if not ladder_summary:
        from app.services.bootstrap.antagonist_roster import format_ladder_summary, load_antagonist_ladder
        ladder = load_antagonist_ladder(project)
        if ladder:
            ladder_summary = format_ladder_summary(ladder)

    char_realm_lines = "\n".join(
        f"- {name}：境界={realm}" for name, realm in char_realms.items()
    )
    hard_precheck_hint = ""
    if precheck_issues:
        hard_precheck_hint = (
            "\n【代码已确认的硬伤（无需重复，专注其余语义矛盾）】\n"
            + "\n".join(f"  - {i['description']}" for i in precheck_issues)
            + "\n"
        )
    faction_hint_block = ""
    if faction_hints:
        faction_hint_block = (
            "\n【代码疑似势力/归属线索 — 须由你裁决，误判则不得写入 JSON】\n"
            "以下由正则从卷叙述中提取，常将「虚空之门」「守门人」「血脉至上的家」等叙事短语"
            "误识别为组织名。请结合【势力档案摘要】与【卷级骨架】全文判断：\n"
            "  - 若为已登记势力的别名/简称 → 忽略\n"
            "  - 若为叙事环境词（门、殿、家等普通用语）→ 忽略\n"
            "  - 若确为未建档的关键组织（如禁契宗）→ 写入 faction_mismatch\n"
            + "\n".join(f"  - {h}" for h in faction_hints)
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

【卷级对立面登记表】
{ladder_summary or '（未设定）'}
{hard_precheck_hint}{faction_hint_block}
请对以上信息做「交叉核验」，找出所有显著矛盾或风险项，返回JSON数组：
[
  {{
    "severity": "high/medium/low",
    "type": "realm_mismatch/faction_mismatch/skill_requirement/storyline_gap/timeline_conflict/villain_alignment/other",
    "description": "具体矛盾描述（30字内）",
    "suggestion": "最简单的修复建议（20字内）"
  }}
]

检查重点：
1. 人物卡 current_realm 是否在境界体系 levels 的合法名称里？
2. 势力一致性：卷骨架与人物 faction 是否与【势力档案摘要】吻合？
   对「代码疑似势力/归属线索」逐条裁决——仅确认真问题才输出 faction_mismatch；
   叙事短语误识别、已登记别名不得列为 issue。
3. 故事线类型与卷骨架冲突走向是否吻合？各故事线是否都能在卷骨架中找到推进节点？
4. 境界体系 protagonist_start_rank 与主角人物卡 current_realm 是否对应同一境界？
5. 反派行动线与卷骨架 phase 标记是否对齐（反派明显占优的卷是否标记了 dark_hour/turning）？
6. 各卷 volume_boss 是否与 antagonist_ladder / 人物库 arc 反派一致？Boss 动机是否与人物卡吻合？
如果没有发现矛盾，返回空数组 []。只返回JSON数组，不要任何解释。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=max_tokens_bootstrap_completion(), task="bootstrap.consistency_scan"
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
