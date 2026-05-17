"""Bootstrap Fanqie Step 10：人物功能表。

番茄人物设计原则：每个角色首要属性是「功能标签」，深度是次要属性。
功能标签决定：何时出场、如何互动、何时退场。

前 5 章出场角色硬约束（算法完读率要求）：
- 第1章：最多 3 个有名字的角色（主角 + 最多 2 个）
- 前3章：最多 5 个有名字的角色
- 前5章：最多 8 个有名字的角色

创建 Character 记录（供后续写章节使用），同时输出登场序列。
"""
from __future__ import annotations

from typing import Any

from app.models import Character, Project
from app.services.bootstrap.parse import parse_json

_FUNCTION_TAGS = (
    "打脸靶_主要 / 打脸靶_次要 / 助力者_前期 / 助力者_后期 / "
    "爱慕对象_正 / 爱慕对象_反 / 搞笑担当 / 导师_显 / 导师_隐 / "
    "大BOSS_前期 / 大BOSS_终极 / 路人_工具"
)


async def gen_character_functions(svc: Any, project: Project, ctx: dict) -> list[Character]:
    """
    生成人物功能表：8-10个角色，每人含功能标签 + 登场章节 + 打脸/助力场景。

    创建 Character 记录并落库；登场序列写入 Project.extra['character_intro_sequence']。

    @returns 已落库 Character 列表
    """
    system = "你是番茄小说人物架构设计师。只返回 JSON 数组，不要解释文字。"
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    contrast = ctx.get("contrast_design") or {}
    fsm = ctx.get("face_slap_map") or {}
    gf = ctx.get("golden_finger") or {}
    ladder = ctx.get("power_ladder") or {}

    slap_targets = [t.get("name", "") for t in (fsm.get("targets") or [])[:5]]
    stages = gf.get("upgrade_stages") or []

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
主角初始状态：{contrast.get('initial_state_headline', '')}
打脸对象顺序：{' → '.join(slap_targets)}
金手指升级阶段数：{len(stages)}
世界权力层级数：{len(ladder.get('social_ladder', []))}
创意：{ctx['logline']}

功能标签参考（必须从下列中选，可组合）：
{_FUNCTION_TAGS}

前5章出场硬约束（必须严格遵守）：
- 第1章：最多3个有名字的角色
- 前3章：最多5个有名字的角色
- 前5章：最多8个有名字的角色

生成8-10个角色，返回 JSON 数组：
[
  {{
    "name": "角色名",
    "function_tag": "从上列功能标签中选最主要的一个",
    "gender": "男/女",
    "age": "年龄（数字）",
    "relation_to_protagonist": "与主角的关系（一句话）",
    "initial_tier": 1,
    "intro_chapter": 1,
    "first_scene": "首次登场的具体场景（做什么事，20字内）",
    "core_role": "在故事中的核心作用（一句话，要具体到'负责在第X章打脸/帮助主角获得某资源'）",
    "reversal_moment": "这个角色最重要的一次转折（如：从嘲讽者变成崇拜者，发生在约第X章，25字内）",
    "personality": "性格（一句话，突出最影响剧情的特质）"
  }}
]

要求：
1. intro_chapter 必须按照前5章出场约束排列，不能所有人都在第1章出场
2. 打脸靶角色的 reversal_moment 必须说明「被打脸的具体方式」
3. 助力者角色的 core_role 必须说明「提供什么具体资源/能力」
4. 只返回 JSON 数组"""

    last_err = ""
    for attempt in range(3):
        fix = f"\n【请修正：{last_err}】" if last_err else ""
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=2048,
            task="bootstrap.characters",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, list) or len(data) < 5:
            last_err = "须为至少5个角色的 JSON 数组"
            continue

        # 落库 Character 记录
        chars: list[Character] = []
        intro_sequence = []
        for item in data:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            char = Character(
                project_id=project.id,
                name=item["name"],
                role=_map_role(item.get("function_tag", "")),
                gender=item.get("gender", ""),
                age=str(item.get("age", "")),
                personality=item.get("personality", ""),
                background=item.get("core_role", ""),
                motivation=item.get("reversal_moment", ""),
                author_notes=item.get("function_tag", ""),  # 存功能标签
                extra={
                    "function_tag": item.get("function_tag", ""),
                    "intro_chapter": item.get("intro_chapter", 1),
                    "first_scene": item.get("first_scene", ""),
                    "relation_to_protagonist": item.get("relation_to_protagonist", ""),
                    "initial_tier": item.get("initial_tier", 1),
                    "reversal_moment": item.get("reversal_moment", ""),
                },
            )
            svc.db.add(char)
            chars.append(char)
            intro_sequence.append({
                "chapter": item.get("intro_chapter", 1),
                "name": item["name"],
                "function_tag": item.get("function_tag", ""),
                "first_scene": item.get("first_scene", ""),
            })
        svc.db.flush()

        # 按登场章节排序
        intro_sequence.sort(key=lambda x: x.get("chapter", 99))

        # 写入 Project.extra
        extra = dict(project.extra or {})
        extra["character_intro_sequence"] = intro_sequence
        project.extra = extra
        svc.db.commit()

        ctx["_char_ids"] = [str(c.id) for c in chars]
        ctx["protagonist"] = next(
            (c.name for c in chars if c.role in ("protagonist", "主角")),
            chars[0].name if chars else "主角",
        )
        return chars

    return []


def _map_role(tag: str) -> str:
    """将番茄功能标签映射到通用 role 字段值。"""
    tag_lower = tag.lower()
    if "主角" in tag or "protagonist" in tag_lower:
        return "protagonist"
    if "boss" in tag_lower or "反派" in tag or "大boss" in tag:
        return "antagonist"
    if "助力" in tag or "导师" in tag:
        return "mentor"
    if "爱慕" in tag or "love" in tag_lower:
        return "love_interest"
    return "supporting"
