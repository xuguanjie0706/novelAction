"""Bootstrap Fanfic：原著人物建档 + 主角槽位 + OC 槽位。

设计要点（与通用线对齐）：
- 必须恰好 1 个 role_type=protagonist（穿书/重生的 POV 锚点，写章 _protagonist_voice_block 依赖）。
- 落库时正确写 Character.role（protagonist/antagonist/supporting），而非仅 extra.role_type。
- 收尾回填 ctx（char_names / protagonist / core_char_names / char_profiles），
  否则下游通用 gen_volumes 的「主线核心角色 / 主角行为驱动」全为空 —— 这是卷骨架盲生成的根因。
- 顺带派生 antagonist_ladder 进 ctx，使复用的 gen_volumes 能把卷级 Boss 绑定到具名角色。
"""
from __future__ import annotations

from typing import Any

from app.models import Character, Project
from app.services.bootstrap.antagonist_roster import normalize_antagonist_ladder
from app.services.bootstrap.json_once import BootstrapStepError, call_bootstrap_json_once
from app.services.bootstrap.steps.fanfic._helpers import fanfic_meta_block, persist_extra
from app.services.outline_planning import words_to_plan

_STEP = "fanfic_canon_characters"


def _role_from_item(item: dict) -> str:
    """role_type + function_tag → Character.role（protagonist/antagonist/supporting）。"""
    rt = (item.get("role_type") or "canon").strip().lower()
    if rt == "protagonist":
        return "protagonist"
    tag = (item.get("function_tag") or "")
    if "BOSS" in tag.upper() or "反派" in tag or "打脸靶" in tag:
        return "antagonist"
    return "supporting"


def _derive_antagonist_ladder(chars: list[Character], ctx: dict, n_volumes: int) -> list[dict]:
    """从已建档反派派生卷级 roster，使 gen_volumes 的 boss 绑定有据可依。"""
    raw: list[dict] = []
    antas = [c for c in chars if c.role == "antagonist"]
    for idx, c in enumerate(antas):
        ex = c.extra or {}
        # 反派数量可能少于卷数；按出场顺序铺到各卷，normalize 会补齐 fallback。
        vi = min(idx, max(0, n_volumes - 1))
        raw.append({
            "vol_index": vi,
            "boss_name": c.name,
            "narrative_function": (ex.get("core_role") or ex.get("function_tag") or "")[:120],
        })
    if not raw:
        return []
    return normalize_antagonist_ladder(raw, ctx, n_volumes)


async def gen_canon_characters(svc: Any, project: Project, ctx: dict) -> list[Character]:
    system = (
        "你是同人人物编辑。必须恰好设定 1 个 role_type=protagonist 主角（穿书/重生/AU 的 POV 锚点，"
        "可以是穿进原著角色身体的人，也可以是 OC）；原著角色须保留名与核心性格；可增 1-2 个 OC。"
        "只返回 JSON 数组。"
    )
    canon = ctx.get("fanfic_canon") or {}
    roster = canon.get("character_roster") or []
    roster_txt = "\n".join(
        f"- {r.get('name')}: {r.get('traits', '')}" for r in roster[:12] if isinstance(r, dict)
    )
    prompt = f"""{fanfic_meta_block(ctx)}
原著人物表：
{roster_txt or '（见梗概）'}

创意：{ctx['logline']}

返回 JSON 数组（8-12 人）：
【硬性约束】
- 恰好 1 人 role_type=protagonist（本书 POV 主角，须给 core_wound / current_desire / current_status / current_location）
- 至少 5 人为原著角色 role_type=canon
- 反派/打脸靶请用 function_tag 标明（含「BOSS」或「打脸靶」字样）
[
  {{
    "name": "姓名",
    "role_type": "protagonist|canon|oc",
    "source_role": "原著身份（OC 写「原创」；穿书主角写穿入对象）",
    "function_tag": "主角_POV|打脸靶_主要|助力者_前期|爱慕对象_正|大BOSS_前期|...",
    "gender": "男/女",
    "relation_to_protagonist": "与主角关系（主角本人写「本人」）",
    "speech_style": "语风（10字内，贴合原著）",
    "personality": "性格一句话",
    "core_wound": "恐惧/创伤（仅主角必填，他人可空）",
    "current_desire": "当前欲望（仅主角必填，他人可空）",
    "current_status": "alive|dead|missing|sealed",
    "current_location": "开局所在地（20字内）",
    "intro_chapter": 1,
    "first_scene": "首次出场场景（20字内）",
    "core_role": "剧情功能（一句话）"
  }}
]"""

    def _validate(data: Any) -> str | None:
        if not isinstance(data, list) or len(data) < 5:
            return "须至少 5 个角色的 JSON 数组"
        return None

    data = await call_bootstrap_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.characters",
        validate=_validate,
    )

    chars: list[Character] = []
    canon_count = 0
    protagonist_count = 0
    for item in data:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        rt = (item.get("role_type") or "canon").strip().lower()
        if rt == "canon":
            canon_count += 1
        if rt == "protagonist":
            protagonist_count += 1
        char = Character(
            project_id=project.id,
            name=str(item["name"])[:64],
            role=_role_from_item(item),
            gender=item.get("gender"),
            personality=(item.get("personality") or "")[:500],
            speech_style=(item.get("speech_style") or "")[:200],
            current_status=(item.get("current_status") or "alive")[:20],
            current_location=(item.get("current_location") or "")[:200] or None,
            extra={
                "role_type": rt,
                "source_role": item.get("source_role", ""),
                "function_tag": item.get("function_tag", ""),
                "core_wound": item.get("core_wound", ""),
                "current_desire": item.get("current_desire", ""),
                "intro_chapter": item.get("intro_chapter", 1),
                "first_scene": item.get("first_scene", ""),
                "core_role": item.get("core_role", ""),
                "relation_to_protagonist": item.get("relation_to_protagonist", ""),
            },
        )
        svc.db.add(char)
        chars.append(char)

    if protagonist_count != 1:
        svc.db.rollback()
        raise BootstrapStepError(
            _STEP,
            f"必须恰好 1 个 role_type=protagonist（当前 {protagonist_count} 个）",
        )
    if canon_count < 3:
        svc.db.rollback()
        raise BootstrapStepError(_STEP, "至少 3 个 role_type=canon 角色")

    svc.db.commit()
    for c in chars:
        svc.db.refresh(c)

    _populate_ctx(project, ctx, chars, svc)
    return chars


def _populate_ctx(project: Project, ctx: dict, chars: list[Character], svc: Any) -> None:
    """回填 ctx + 落库引导序列 + 派生反派 roster（修复卷骨架盲生成）。"""
    intro = [
        {"name": c.name, "chapter": (c.extra or {}).get("intro_chapter", 1)}
        for c in chars
    ]
    persist_extra(project, svc, "character_intro_sequence", intro)
    ctx["_char_ids"] = [str(c.id) for c in chars]

    ctx["char_names"] = [c.name for c in chars]
    protagonist = next((c for c in chars if c.role == "protagonist"), None)
    ctx["protagonist"] = protagonist.name if protagonist else (chars[0].name if chars else "主角")
    ctx["core_char_names"] = [
        c.name for c in chars
        if c.role in ("protagonist", "antagonist")
        or "助力" in ((c.extra or {}).get("function_tag") or "")
        or "爱慕" in ((c.extra or {}).get("function_tag") or "")
    ][:8]
    ctx["char_profiles"] = {
        c.name: {
            "core_wound": (c.extra or {}).get("core_wound", ""),
            "current_desire": (c.extra or {}).get("current_desire", ""),
            "role": c.role,
        }
        for c in chars
    }

    tw = int(project.target_words or 1_200_000)
    n_volumes = words_to_plan(tw)["total_volumes"]
    ladder = _derive_antagonist_ladder(chars, ctx, n_volumes)
    if ladder:
        ctx["antagonist_ladder"] = ladder
        persist_extra(project, svc, "antagonist_ladder", ladder)
