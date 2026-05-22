"""
location_debrief.py — 复盘触发的地点自动入库服务

设计动机：
  Bootstrap 阶段没有正文语境，生成的感官基准质量差；
  让 AI 在复盘时（已读完整章内容）自动为"首次出现的地点"生成
  sensory_signature / danger_level / location_type，
  写入 Location 台账，供后续章节的空间连续性约束（_build_location_context）使用。

调用方：
  debrief_routes.chapter_debrief 在 db.commit() 后，通过 schedule_background_coro
  fire-and-forget 调用 enrich_new_locations；失败只记 warning，不影响主流程。

输出标记：
  自动生成的记录在 extra["source"] = "auto_debrief" 中打标，
  前端 LocationsTab 据此显示「复盘自动」徽章，方便作者辨认并手工修订。
"""

from __future__ import annotations

import json
import logging
from typing import Optional
from uuid import UUID

from openai import AsyncOpenAI

from app.models.location import Location
from app.services.bootstrap.parse import parse_json
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection

logger = logging.getLogger(__name__)

# 单次最多处理地点数，避免单章大量跳场时 token 爆炸
_MAX_LOCATIONS_PER_CALL = 6

# 合法 location_type / danger_level 白名单（防 AI 幻想值入库）
_VALID_TYPES = {
    "indoor", "outdoor", "ruins", "battlefield",
    "wilderness", "sacred_ground", "city", "dungeon", "void",
}
_VALID_DANGERS = {"safe", "neutral", "dangerous", "forbidden"}


def _build_prompt(
    location_entries: list[dict],
    chapter_content: str,
    chapter_title: str,
) -> str:
    """
    构造给 AI 的一次性批量地点分析 prompt。

    @param location_entries: [{"name": str, "char_name": str}, ...]
    @param chapter_content:  章节正文（用于感官细节提取）
    @param chapter_title:    章节标题（上下文信息）
    @returns 格式化 prompt 字符串
    """
    names_block = "\n".join(
        f'  {i+1}. "{e["name"]}"（出现在角色：{e["char_name"]}）'
        for i, e in enumerate(location_entries)
    )
    # 正文截取前 3000 字，保留地点出现的主要语境
    content_excerpt = chapter_content[:3000].strip()

    return f"""你是一位资深玄幻/仙侠网文编辑，正在为小说建立地点台账。

【章节标题】{chapter_title}
【章节正文节选（前3000字）】
{content_excerpt}
---

根据上方正文，为以下地点生成结构化描述。若正文中该地点描写不足，可合理推断补全，但须与正文已有内容一致。

需要生成的地点：
{names_block}

请严格按如下 JSON 数组格式返回，不要输出其他任何内容：
[
  {{
    "name": "与输入完全相同的地点名",
    "sensory_signature": "1-3句固定感官基准：气味、光线、声音、温度（用于写章时的硬约束，禁止含人物动作）",
    "location_type": "indoor|outdoor|ruins|battlefield|wilderness|sacred_ground|city|dungeon|void 之一",
    "danger_level": "safe|neutral|dangerous|forbidden 之一",
    "description": "1-2句地点背景描述（控制方/历史/用途）"
  }}
]

重要规则：
- sensory_signature 只写环境本身的固定感知，不写角色行为；长度15~60字
- location_type / danger_level 必须从括号内的枚举值中选一个，不得自造
- 只返回 JSON 数组，不加 markdown fence 或任何解释
"""


def _coerce_location_data(raw: dict) -> dict | None:
    """
    对 AI 返回的单条地点数据做字段校验和裁剪。

    @returns 合法的地点 dict，或 None（若名称为空则丢弃）
    """
    name = (raw.get("name") or "").strip()[:100]
    if not name:
        return None

    loc_type = (raw.get("location_type") or "indoor").strip()
    if loc_type not in _VALID_TYPES:
        loc_type = "indoor"

    danger = (raw.get("danger_level") or "neutral").strip()
    if danger not in _VALID_DANGERS:
        danger = "neutral"

    sensory = (raw.get("sensory_signature") or "").strip()[:300]
    description = (raw.get("description") or "").strip()[:500]

    return {
        "name": name,
        "location_type": loc_type,
        "danger_level": danger,
        "sensory_signature": sensory or None,
        "description": description or None,
    }


def _match_existing(loc_name: str, all_locs: list[Location]) -> Location | None:
    """
    按名称精确匹配 → 别名精确匹配 → 子串模糊匹配，返回已有 Location 或 None。
    """
    lower = loc_name.lower()
    for l in all_locs:
        if l.name.lower() == lower:
            return l
    for l in all_locs:
        aliases = l.aliases or []
        if any(a.lower() == lower for a in aliases):
            return l
    for l in all_locs:
        if l.name.lower() in lower or lower in l.name.lower():
            return l
    return None


async def enrich_new_locations(
    project_id: str,
    location_entries: list[dict],
    chapter_content: str,
    chapter_title: str,
    model_profile: str,
    llm_provider_id: Optional[UUID],
) -> None:
    """
    复盘后台任务：为本章出现的新地点生成感官基准并写入 Location 台账。

    逻辑：
    1. 去重 location_entries（同名合并）
    2. 与项目内现有 Location 比对：已有且有 sensory_signature 的跳过
    3. 对剩余地点，调用 AI 批量生成结构化描述
    4. 存入 Location 表，并在 extra["source"] 打标 "auto_debrief"

    @param project_id:       项目 UUID 字符串
    @param location_entries: [{"name": str, "char_name": str}, ...]
    @param chapter_content:  章节正文（供 AI 提取感官细节用）
    @param chapter_title:    章节标题
    @param model_profile:    "gemini" 或 "local"
    @param llm_provider_id:  远程线路 UUID（可为 None）
    """
    if not location_entries:
        return

    # 去重（保留首次出现的 char_name 作为上下文）
    seen: dict[str, dict] = {}
    for entry in location_entries:
        name = (entry.get("name") or "").strip()
        if name and name not in seen:
            seen[name] = entry
    unique_entries = list(seen.values())[:_MAX_LOCATIONS_PER_CALL]

    try:
        from app.database import SessionLocal
        with SessionLocal() as db:
            # 预加载项目内所有 Location，用于去重判断
            existing_locs: list[Location] = (
                db.query(Location)
                .filter(Location.project_id == project_id)
                .all()
            )

            # 筛选出需要新建或补全 sensory_signature 的地点
            to_enrich: list[dict] = []
            to_update: list[tuple[Location, dict]] = []  # (existing_loc, entry)

            for entry in unique_entries:
                match = _match_existing(entry["name"], existing_locs)
                if match is None:
                    to_enrich.append(entry)
                elif not (match.sensory_signature or "").strip():
                    # 已有地点但缺感官基准，补全
                    to_update.append((match, entry))

            if not to_enrich and not to_update:
                logger.info(
                    "location_debrief: project %s — all %d locations already enriched, skip",
                    project_id, len(unique_entries),
                )
                return

            all_to_call = to_enrich + [e for _, e in to_update]
            logger.info(
                "location_debrief: project %s — calling AI for %d locations (%d new, %d to update)",
                project_id, len(all_to_call), len(to_enrich), len(to_update),
            )

            # ── AI 调用 ──────────────────────────────────────────────────────────
            ai_results = await _call_ai_for_locations(
                location_entries=all_to_call,
                chapter_content=chapter_content,
                chapter_title=chapter_title,
                model_profile=model_profile,
                llm_provider_id=llm_provider_id,
            )
            if not ai_results:
                logger.warning("location_debrief: AI returned empty for project %s", project_id)
                return

            # ── 持久化 ───────────────────────────────────────────────────────────
            # key 用 entry["name"]（与 AI 回写名称一致），value 为已匹配的 Location 行
            _persist_locations(
                db=db,
                project_id=project_id,
                ai_results=ai_results,
                to_enrich_names={e["name"] for e in to_enrich},
                to_update_map={e["name"]: loc for loc, e in to_update},
            )

    except Exception as exc:  # noqa: BLE001
        logger.warning("location_debrief failed for project %s: %s", project_id, exc)


async def _call_ai_for_locations(
    location_entries: list[dict],
    chapter_content: str,
    chapter_title: str,
    model_profile: str,
    llm_provider_id: Optional[UUID],
) -> list[dict]:
    """
    调用 LLM 批量生成地点描述，返回经过校验的 dict 列表。
    失败时返回空列表，不抛出异常（由调用方记 warning）。
    """
    from app.database import SessionLocal
    from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection
    from app.config import settings

    # 解析连接参数（与 debrief_routes 同逻辑）
    if llm_provider_id:
        from app.models import LlmProvider
        with SessionLocal() as db2:
            provider = db2.query(LlmProvider).filter(
                LlmProvider.id == llm_provider_id
            ).first()
        if provider:
            base_url = normalize_openai_base_url(provider.base_url or "")
            api_key = provider.api_key or "sk-placeholder"
            model_name = provider.model_name or "gemini-2.0-flash"
        else:
            base_url, api_key, model_name = _fallback_connection(model_profile, settings)
    else:
        base_url, api_key, model_name = _fallback_connection(model_profile, settings)

    prompt = _build_prompt(location_entries, chapter_content, chapter_title)

    try:
        client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,   # 地点描述需要稳定
            max_tokens=1500,
        )
        raw_text = (resp.choices[0].message.content or "").strip()
        parsed = parse_json(raw_text)
        if not isinstance(parsed, list):
            parsed = [parsed] if isinstance(parsed, dict) else []
        results = []
        for item in parsed:
            coerced = _coerce_location_data(item) if isinstance(item, dict) else None
            if coerced:
                results.append(coerced)
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("location_debrief AI call failed: %s", exc)
        return []


def _fallback_connection(model_profile: str, settings) -> tuple[str, str, str]:
    """无 llm_provider_id 时回退到环境变量连接。"""
    from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection
    if model_profile == "gemini":
        base_url, api_key, model_name = resolve_gemini_connection(settings)
    else:
        base_url = normalize_openai_base_url(settings.LLM_BASE_URL or "")
        api_key = settings.LLM_API_KEY or "sk-placeholder"
        model_name = settings.AI_MODEL or "gemini-2.0-flash"
    return base_url, api_key, model_name


def _persist_locations(
    db,
    project_id: str,
    ai_results: list[dict],
    to_enrich_names: set[str],
    to_update_map: dict[str, Location],
) -> None:
    """
    将 AI 生成结果写入 Location 表。

    新建：to_enrich_names 中的地点 → INSERT，extra["source"]="auto_debrief"
    补全：to_update_map 中的地点  → 仅补填 sensory_signature 等空字段，不覆盖作者手填内容

    @param db:              SQLAlchemy Session（独立，由调用方管理）
    @param project_id:      项目 UUID 字符串
    @param ai_results:      AI 返回并经过校验的地点 dict 列表
    @param to_enrich_names: 需要新建的地点名称集合
    @param to_update_map:   entry 名称 → Location 映射（key 与 AI 返回 name 一致，非 DB 行名）
    """
    created = 0
    updated = 0

    for loc_data in ai_results:
        name = loc_data["name"]

        if name in to_enrich_names:
            # 新建
            new_loc = Location(
                project_id=project_id,
                name=name,
                location_type=loc_data.get("location_type") or "indoor",
                danger_level=loc_data.get("danger_level") or "neutral",
                sensory_signature=loc_data.get("sensory_signature"),
                description=loc_data.get("description"),
                extra={"source": "auto_debrief"},
            )
            db.add(new_loc)
            created += 1

        elif name in to_update_map:
            # 补全：只填空字段，不覆盖作者手写内容
            existing = to_update_map[name]
            if not (existing.sensory_signature or "").strip():
                existing.sensory_signature = loc_data.get("sensory_signature")
            if not (existing.description or "").strip():
                existing.description = loc_data.get("description")
            if not (existing.location_type or "").strip() or existing.location_type == "indoor":
                existing.location_type = loc_data.get("location_type") or existing.location_type
            if not (existing.danger_level or "").strip() or existing.danger_level == "neutral":
                existing.danger_level = loc_data.get("danger_level") or existing.danger_level
            # 补全时同样打标（区分来源）
            existing_extra = dict(existing.extra) if isinstance(existing.extra, dict) else {}
            if "source" not in existing_extra:
                existing_extra["source"] = "auto_debrief"
                existing.extra = existing_extra
            updated += 1

    try:
        db.commit()
        logger.info(
            "location_debrief: project %s — %d created, %d updated",
            project_id, created, updated,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("location_debrief persist failed for project %s: %s", project_id, exc)
