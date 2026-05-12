"""Bootstrap 方案 B：单次全量 JSON 补齐（缺失设定卡 / 人物）。"""

from __future__ import annotations

import json

from app.config import settings
from app.services.ai_service import AIService
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts import CHARACTER_TARGET, GEMINI_SETTING_BLUEPRINTS


async def complete_single_shot_data(ai: AIService, data: dict, logline: str, premise: str = "") -> dict:
    """单次生成若少给关键数组，保存前按同一规格补齐。"""
    if not isinstance(data, dict):
        return data

    data.setdefault("settings", [])
    data.setdefault("characters", [])
    data["settings"] = await complete_missing_settings(ai, data, logline, premise)
    data["characters"] = await complete_missing_characters(ai, data, logline, premise)
    return data


async def complete_missing_settings(ai: AIService, data: dict, logline: str, premise: str = "") -> list:
    existing = data.get("settings") or []
    existing_titles = {
        item.get("title")
        for item in existing
        if isinstance(item, dict) and item.get("title")
    }
    missing_blueprints = [
        bp for bp in GEMINI_SETTING_BLUEPRINTS
        if bp["title"] not in existing_titles
    ]
    if not missing_blueprints:
        return existing

    system = "你是网络小说世界观设计专家。只返回JSON数组。"
    prompt = f"""补齐缺失的世界设定卡。

创意：{logline}
立意与类型：{premise[:2000] or data.get('project', {}).get('premise', '')[:2000]}
项目基础：{json.dumps(data.get('project', {}), ensure_ascii=False)[:4000]}
已有设定标题：{json.dumps(sorted(existing_titles), ensure_ascii=False)}

只生成以下缺失蓝图对应的设定卡：
{json.dumps(missing_blueprints, ensure_ascii=False, indent=2)}

返回JSON数组。每张卡字段：
title, content, tags, extra。
要求：
1) title/category/tags/importance/stage 必须与蓝图一致，写入 extra。
2) "作品立意" 必须填写 extra.core 全字段。
3) 其他卡必须填写 extra.focus 全字段：summary, story_function, conflict_seed, cost_or_risk, affected_people, exception_or_loophole, visual_anchor。
4) content 至少180字，要有名词、地点、制度、代价、例外或冲突。
只返回JSON数组，不要解释。"""
    raw = await ai._call_ai(
        system,
        prompt,
        max_tokens=settings.GEMINI_SETTING_COMPLETION_MAX_TOKENS,
        context={"operation": "bootstrap_complete_settings"},
    )
    parsed = parse_json(raw)
    if not isinstance(parsed, list):
        parsed = parsed.get("settings", [])
    completed = [
        item for item in parsed
        if isinstance(item, dict) and item.get("title") not in existing_titles
    ]
    return [*existing, *completed]


async def complete_missing_characters(ai: AIService, data: dict, logline: str, premise: str = "") -> list:
    existing = data.get("characters") or []
    existing_names = {
        item.get("name")
        for item in existing
        if isinstance(item, dict) and item.get("name")
    }
    missing_count = max(0, CHARACTER_TARGET - len(existing))
    if missing_count <= 0:
        return existing

    system = "你是网络小说人物设计专家。只返回JSON数组。"
    prompt = f"""补齐缺失的人物档案。

创意：{logline}
立意与类型：{premise[:1600] or data.get('project', {}).get('premise', '')[:1600]}
项目基础：{json.dumps(data.get('project', {}), ensure_ascii=False)[:3000]}
已有人物：{json.dumps(existing, ensure_ascii=False)[:6000]}
已有人物名禁止重复：{json.dumps(sorted(existing_names), ensure_ascii=False)}

还需要生成 {missing_count} 个人物，使总人物数达到 {CHARACTER_TARGET} 个。
总阵容目标：1 主角、3 核心配角、2 反派、2 师长/势力角色。

返回JSON数组。每个人物字段：
name, role, gender, age, faction, personality, background, motivation, arc, current_realm,
speech_style, values, fear, secrets, strengths, weaknesses, special_traits。
role 只能是 protagonist / supporting / antagonist。
只返回JSON数组，不要解释。"""
    raw = await ai._call_ai(
        system,
        prompt,
        max_tokens=settings.BOOTSTRAP_COMPLETION_MAX_TOKENS,
        context={"operation": "bootstrap_complete_characters"},
    )
    parsed = parse_json(raw)
    if not isinstance(parsed, list):
        parsed = parsed.get("characters", [])
    completed = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name or name in existing_names:
            continue
        completed.append(item)
        existing_names.add(name)
        if len(existing) + len(completed) >= CHARACTER_TARGET:
            break
    return [*existing, *completed]
