"""
Character Gap Check — 章节大纲细化前的角色缺口检测

职责：
  1. 分析即将细化的卷/篇大纲，判断现有角色库是否覆盖所需"职能角色"
  2. 若存在缺口，生成新配角档案并写入数据库（character_tier="supporting"/"emergent"）
  3. 返回新增角色列表，供调用方更新 char_summary

设计原则：
  - 轻量 prompt：专注职能缺口检测，不重复生成已有信息
  - 新角色默认低权重：不侵占主线人物成长线，每章至少1个主线角色承担推进职责
  - 数量控制：每次检测最多新增 3 个配角（防止人物表膨胀失控）
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.character import Character
from app.services.bootstrap.prompts.character_naming import character_naming_constraints_for_prompt

if TYPE_CHECKING:
    from app.services.ai_service import AIService


# ─────────────────────────────────────────────────────────────
#  工具函数
# ─────────────────────────────────────────────────────────────

def _parse_json_safe(raw: str) -> list | dict:
    """提取并解析 JSON，容错 markdown fence 和多余空白。"""
    text = raw.strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if "```" in text:
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if fence:
            text = fence.group(1).strip()
    # 去掉尾部多余文字（只保留第一个完整 JSON 块）
    for end_char in ("]", "}"):
        idx = text.rfind(end_char)
        if idx != -1:
            text = text[: idx + 1]
            break
    try:
        return json.loads(text)
    except Exception:
        return []


def _build_core_cast_summary(characters: list[Character]) -> str:
    """把现有角色压缩成紧凑摘要，供 prompt 使用。"""
    lines = []
    for c in characters:
        tier_label = "【核心】" if (c.character_tier or "core") == "core" else "【配角】"
        parts = [f"{tier_label}{c.name}（{c.role or 'supporting'}）"]
        if c.faction:
            parts.append(f"阵营={c.faction}")
        if c.current_realm:
            parts.append(f"境界={c.current_realm}")
        if c.motivation:
            parts.append(f"动机={c.motivation[:40]}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
#  Step 1 — 缺口检测
# ─────────────────────────────────────────────────────────────

async def character_gap_check(
    *,
    volume_title: str,
    volume_summary: str,
    volume_conflict: str,
    existing_characters: list[Character],
    ai_svc: "AIService",
) -> list[dict]:
    """
    检测卷/篇大纲在现有角色库下是否存在职能缺口。

    返回 new_character_request 列表，每项结构：
    {
      "role_function": "职能描述，如「城门守卫队长」",
      "arc_scope": "single_chapter | mini_arc | long_arc",
      "required_relations": "与哪位主线角色直接产生关系",
      "entry_chapter_hint": "预计在第几章附近出场",
      "character_tier": "supporting | emergent",
      "reason": "为什么现有角色无法覆盖此职能"
    }
    空列表 = 无缺口，无需新增角色。
    """
    cast_summary = _build_core_cast_summary(existing_characters)

    system = "你是网络小说人物架构分析专家。只返回JSON数组，不要任何解释文字。"
    prompt = f"""分析以下卷级大纲，判断现有角色库是否存在「职能缺口」。

【卷标题】{volume_title}
【卷概述】{volume_summary or '（未填写）'}
【核心冲突】{volume_conflict or '（未填写）'}

【现有角色库】
{cast_summary}

职能缺口 = 本卷剧情推进需要某类角色（如：线人、反派执行人、见证者、权威裁判者、情报渠道等），
但现有角色因阵营/地理/年龄/动机冲突，无法合理承担该职能。

判断标准（必须同时满足才算缺口）：
1. 本卷 summary/conflict 明确暗示需要此职能
2. 现有角色库无法在不破坏其设定的前提下承担
3. 缺少此角色会导致剧情无法合理推进

最多识别 3 个缺口。若无真实缺口，返回空数组 []。

返回格式（JSON数组）：
[
  {{
    "role_function": "职能描述（具体，如「将军麾下传令官」而非「传令官」）",
    "arc_scope": "single_chapter",
    "required_relations": "与[主线角色名]产生[关系类型]",
    "entry_chapter_hint": "第X卷前期/中期/后期",
    "character_tier": "supporting",
    "reason": "为何现有角色无法覆盖（一句话）"
  }}
]
只返回JSON数组，不要任何说明文字。"""

    raw = await ai_svc._call_ai(system, prompt, max_tokens=600)
    result = _parse_json_safe(raw)
    if not isinstance(result, list):
        return []
    # 过滤掉格式不对的项，并限制数量
    valid = [
        item for item in result
        if isinstance(item, dict) and item.get("role_function")
    ]
    return valid[:3]


# ─────────────────────────────────────────────────────────────
#  Step 2 — 创建配角
# ─────────────────────────────────────────────────────────────

async def create_supporting_character(
    *,
    project_id: UUID,
    request: dict,
    existing_characters: list[Character],
    genre: str,
    ai_svc: "AIService",
    db: Session,
) -> Character | None:
    """
    根据缺口请求生成并持久化一个新配角。

    约束：
    - 不侵占主线角色成长线
    - 默认 character_tier = request.get("character_tier", "supporting")
    - 每章出场仍需有主线角色承担推进职责
    """
    existing_names = [c.name for c in existing_characters]
    cast_summary = _build_core_cast_summary(existing_characters)
    tier = request.get("character_tier", "supporting")
    naming_block = character_naming_constraints_for_prompt(
        genre,
        existing_names=existing_names,
        require_name_meaning=True,
    )

    system = "你是网络小说人物设计专家。只返回JSON对象，不要任何解释文字。"
    prompt = f"""为小说（{genre}）创建一个配角档案。

【职能需求】{request.get('role_function', '')}
【出场范围】{request.get('arc_scope', 'mini_arc')}
【关系要求】{request.get('required_relations', '')}
【出场时机】{request.get('entry_chapter_hint', '')}

【现有主线角色（不得重名，不得设定与其冲突的成长线）】
{cast_summary}

{naming_block}

【设计约束】
- 这是配角，不是主线角色，不能抢主角风头
- arc_scope="single_chapter" 时，动机简单、无复杂背景

返回 JSON 对象：
{{
  "name": "姓名（姓+名，2~4字）",
  "name_meaning": "取名寓意（15~40字）",
  "alias": ["可选外号/乳名"],
  "role": "supporting",
  "gender": "男/女",
  "age": "年龄",
  "faction": "所属势力或机构",
  "personality": "性格（1句话）",
  "motivation": "在本卷/本章的行为动机",
  "background": "背景（1句话，不要过于复杂）",
  "current_realm": "境界或能力层级",
  "author_notes": "给作者的提醒（此角色应如何使用，何时退出）"
}}
只返回JSON对象，不要任何说明文字。"""

    raw = await ai_svc._call_ai(system, prompt, max_tokens=500)
    data = _parse_json_safe(raw)
    if not isinstance(data, dict) or not data.get("name"):
        return None

    # 防止重名
    name = data.get("name", "未命名配角")
    if name in existing_names:
        name = f"{name}（{tier}）"

    char_extra: dict = {}
    name_meaning = (data.get("name_meaning") or "").strip()
    if name_meaning:
        char_extra["name_meaning"] = name_meaning
    raw_alias = data.get("alias")
    alias_list = (
        [a.strip() for a in raw_alias if isinstance(a, str) and a.strip()]
        if isinstance(raw_alias, list)
        else []
    )

    char = Character(
        project_id=project_id,
        name=name,
        alias=alias_list or None,
        role=data.get("role", "supporting"),
        character_tier=tier,
        gender=data.get("gender"),
        age=data.get("age"),
        faction=data.get("faction"),
        personality=data.get("personality"),
        background=data.get("background"),
        motivation=data.get("motivation"),
        current_realm=data.get("current_realm"),
        author_notes=data.get("author_notes"),
        extra=char_extra or None,
    )
    db.add(char)
    db.commit()
    db.refresh(char)
    return char


# ─────────────────────────────────────────────────────────────
#  便捷入口：检测 + 批量创建
# ─────────────────────────────────────────────────────────────

async def fill_character_gaps(
    *,
    project_id: UUID,
    volume_title: str,
    volume_summary: str,
    volume_conflict: str,
    genre: str,
    db: Session,
    ai_svc: "AIService",
) -> list[Character]:
    """
    一步完成：检测缺口 → 创建缺失配角 → 返回新增角色列表。
    调用方可将新角色追加进 char_summary 再传给 expand_outline。
    """
    existing = db.query(Character).filter(
        Character.project_id == project_id
    ).all()

    gaps = await character_gap_check(
        volume_title=volume_title,
        volume_summary=volume_summary,
        volume_conflict=volume_conflict,
        existing_characters=existing,
        ai_svc=ai_svc,
    )

    if not gaps:
        return []

    new_chars: list[Character] = []
    # 每次检测后重新读取，避免重名（循环创建时 existing 会增长）
    current_existing = list(existing)
    for gap in gaps:
        char = await create_supporting_character(
            project_id=project_id,
            request=gap,
            existing_characters=current_existing,
            genre=genre,
            ai_svc=ai_svc,
            db=db,
        )
        if char:
            new_chars.append(char)
            current_existing.append(char)

    return new_chars
