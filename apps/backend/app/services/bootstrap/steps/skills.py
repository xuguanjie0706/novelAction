"""Bootstrap Step 6：核心功法技能。"""

from __future__ import annotations

import logging
import uuid as _uuid_module
from typing import Any

from app.models import Project, Skill
from app.services.bootstrap.context import get_genre_kit_block
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.power_registry import format_power_context_block
from app.services.bootstrap.power_grade_align import enrich_skill_power_fields
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


def _build_char_realm_hint(ctx: dict, *, db=None, project_id: str | None = None) -> str:
    """为 skill prompt 生成人物当前境界 rank 速查表，防止 AI 把高阶技能分配给低境界角色。"""
    power_level_names: list[str] = ctx.get("power_level_names") or []
    rank_map = {name: i for i, name in enumerate(power_level_names)}
    registry: dict = ctx.get("power_level_registry") or {}
    char_id_list: list[dict] = ctx.get("char_id_list") or []

    from app.models import Character
    chars_by_name: dict[str, Character] = {}
    # 从 DB 拉取人物境界；禁止把 Session 写入 ctx（会破坏 LangGraph checkpoint）
    pid = project_id or ctx.get("project_id")
    try:
        if db is not None and pid:
            from app.models import Character as _C
            for c in db.query(_C).filter(_C.project_id == pid).all():
                chars_by_name[c.name] = c
    except Exception:
        pass

    lines: list[str] = []
    for entry in char_id_list[:10]:
        name = entry.get("name", "")
        cid = entry.get("id", "")
        char = chars_by_name.get(name)
        realm = (char.current_realm if char else None) or ctx.get("char_realms", {}).get(name, "")
        rank = -1
        if char and char.realm_rank is not None:
            rank = int(char.realm_rank)
        elif realm:
            from app.services.bootstrap.power_registry import resolve_realm_in_registry
            resolved = resolve_realm_in_registry(realm, registry) if registry else realm
            rank = rank_map.get(resolved or realm, -1)
        rank_str = f"rank={rank}" if rank >= 0 else "rank=?"
        lines.append(f"  {name}（{cid}）：{realm or '未知'}（{rank_str}）")

    if not lines:
        return ""
    return (
        "\n【人物当前境界速查（用于判断 mastered_by 合法性）】\n"
        + "\n".join(lines)
        + "\n"
    )


async def gen_key_skills(svc: Any, project: Project, ctx: dict):
    system = "你是网络小说世界构建专家。只返回JSON数组。"
    kit_block = get_genre_kit_block(ctx)
    char_id_hint = ", ".join(
        f"{c['name']}（id={c['id']}）" for c in ctx.get("char_id_list", [])[:8]
    ) or "（人物列表待生成）"
    # 注入人物当前境界速查，供 mastered_by 合法性判断
    ctx["project_id"] = str(project.id)
    char_realm_hint = _build_char_realm_hint(
        ctx, db=svc.db, project_id=str(project.id),
    )
    prompt = f"""{kit_block}小说：《{ctx['project_title']}》({ctx['genre']})
主角：{ctx.get('protagonist', '主角')}
{format_power_context_block(ctx)}
{char_realm_hint}
【器物/道途对齐】若本书有多轴体系：grade 须与主轴境界匹配；填写 required_realm（主轴精确境界名）、artifact_tier（器物阶名）、required_path（sword/pill/body 等）、required_path_rank（道途阶名）。
主要人物（姓名+UUID）：{char_id_hint}

【流派编辑手册约束】
- 技能效果与获取方式必须符合 genre_kit 的 satisfaction_tropes（玄幻强调金手指新用法，仙侠强调心魔/渡劫相关）

【⚠️ mastered_by_character_ids 铁律】
- 只能填写当前境界 rank ≥ 本技能 level_required 对应 rank 的人物 UUID
- 境界不足的人物必须设为空数组 []，并在 plot_hook 中注明「第X卷习得」
- 反派标志性技能若反派尚未登场，mastered_by_character_ids 同样填 []，plot_hook 说明首次使用章节

生成本小说最关键的5~8个功法/技能，返回JSON数组：
[
  {{
    "name": "功法/技能名称",
    "skill_type": "combat",
    "grade": "earth",
    "source": "来源（如：上古秘典、宗门传承）",
    "level_required": "修炼要求（主轴境界名，须从上方列表精确选择）",
    "required_realm": "同 level_required，主轴境界 canonical 名",
    "artifact_tier": "所需器物阶（如灵宝，从器物轴选择，可选）",
    "required_path": "所需道途 path_id（sword/pill/body 等，可选）",
    "required_path_rank": "道途阶位名（从道途轴选择，可选）",
    "description": "功法/技能描述（40字内）",
    "effects": "使用效果",
    "limitations": "使用限制或副作用",
    "mastered_by_character_ids": ["仅填境界已达标的人物UUID；未达标者填空数组[]"],
    "mastered_by_names": ["对应的人物姓名（可选，用于人工核对）"],
    "plot_hook": "剧情钩子：境界未达标者须注明「第X卷习得」；已掌握者说明何时会被损毁/夺走/超越"
  }}
]
skill_type 只能是: combat / defense / movement / support / bloodline / special
grade 只能是: mortal / earth / sky / profound / saint / divine / supreme
选择对故事最重要的技能，包含主角核心战技和1~2个反派标志性技能。
每个技能必须填写 plot_hook，不得留空。
只返回JSON数组，不要说明文字。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.skills",
    )
    data = parse_json(raw)
    if not isinstance(data, list):
        data = data.get("skills", [])

    # 预构建 char_id → realm_rank 速查表，用于落库前过滤境界不足的分配
    _char_rank_by_id: dict[str, int] = {}
    _char_realm_by_id: dict[str, str] = {}
    try:
        from app.models import Character as _Char
        from app.services.bootstrap.power_registry import resolve_realm_in_registry
        _power_level_names: list[str] = ctx.get("power_level_names") or []
        _rank_map = {name: i for i, name in enumerate(_power_level_names)}
        _registry: dict = ctx.get("power_level_registry") or {}
        for _c in svc.db.query(_Char).filter(_Char.project_id == project.id).all():
            _cid = str(_c.id)
            _realm_rank = _c.realm_rank
            if _realm_rank is None and _c.current_realm:
                _resolved = resolve_realm_in_registry(_c.current_realm, _registry) if _registry else _c.current_realm
                _realm_rank = _rank_map.get(_resolved or _c.current_realm)
            if _realm_rank is not None:
                _char_rank_by_id[_cid] = int(_realm_rank)
            if _c.current_realm:
                _char_realm_by_id[_cid] = _c.current_realm
    except Exception:
        logger.exception("skills: 预构建 char_rank_by_id 失败，跳过境界校验")

    char_name_to_id: dict = ctx.get("char_name_to_id", {})
    results = []
    for i, item in enumerate(data):
        raw_ids = item.get("mastered_by_character_ids") or item.get("mastered_by", [])
        mastered_ids = []
        for val in raw_ids:
            if isinstance(val, str):
                try:
                    _uuid_module.UUID(val)
                    mastered_ids.append(val)
                except ValueError:
                    mapped = char_name_to_id.get(val)
                    if mapped:
                        logger.warning(
                            "Skill '%s' mastered_by: AI 输出名字 '%s' 而非 UUID，已回退映射到 %s",
                            item.get("name", "?"), val, mapped,
                        )
                        mastered_ids.append(mapped)
                    else:
                        logger.warning(
                            "Skill '%s' mastered_by: AI 输出 '%s' 既非 UUID 也不在人物列表，已丢弃",
                            item.get("name", "?"), val,
                        )
        skill_extra = {}
        if item.get("plot_hook"):
            skill_extra["plot_hook"] = str(item["plot_hook"])[:300]
        aligned = enrich_skill_power_fields(item, ctx)
        level_required = aligned.get("level_required") or item.get("level_required")
        for k in ("power_ref", "artifact_tier", "path_ref"):
            if aligned.get(k) is not None:
                skill_extra[k] = aligned[k]

        # ── 境界校验：过滤 realm_rank 未达标的分配 ──────────────────────────
        # AI 可能仍然把低境界人物写入 mastered_by，这里作为兜底防线
        if mastered_ids and level_required and _char_rank_by_id:
            _power_level_names_local: list[str] = ctx.get("power_level_names") or []
            _rank_map_local = {name: j for j, name in enumerate(_power_level_names_local)}
            _registry_local: dict = ctx.get("power_level_registry") or {}
            try:
                from app.services.bootstrap.power_registry import resolve_realm_in_registry
                _req_resolved = resolve_realm_in_registry(level_required, _registry_local) if _registry_local else level_required
                _req_rank = _rank_map_local.get(_req_resolved or level_required, -1)
            except Exception:
                _req_rank = -1
            if _req_rank >= 0:
                _filtered: list[str] = []
                for _cid in mastered_ids:
                    _char_rank = _char_rank_by_id.get(_cid)
                    if _char_rank is not None and _char_rank >= _req_rank:
                        _filtered.append(_cid)
                    else:
                        logger.warning(
                            "Skill '%s'（level_required=%s rank=%d）: 人物 %s（realm=%s rank=%s）境界不足，"
                            "已从 mastered_by_character_ids 移除",
                            item.get("name", "?"), level_required, _req_rank,
                            _cid, _char_realm_by_id.get(_cid, "?"),
                            _char_rank if _char_rank is not None else "?",
                        )
                mastered_ids = _filtered
        # ────────────────────────────────────────────────────────────────────

        sk = Skill(
            project_id=project.id,
            name=item.get("name", f"功法{i+1}"),
            skill_type=item.get("skill_type", "combat"),
            grade=item.get("grade", "earth"),
            source=item.get("source"),
            level_required=level_required,
            description=item.get("description"),
            effects=item.get("effects"),
            limitations=item.get("limitations"),
            mastered_by_character_ids=mastered_ids,
            sort_order=i,
            extra=skill_extra,
        )
        svc.db.add(sk)
        results.append(sk)

    svc.db.commit()
    ctx["skill_names"] = [sk.name for sk in results]
    return results
