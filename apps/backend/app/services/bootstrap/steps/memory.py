"""Bootstrap Step 10：记忆库种子。"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models import MemoryChunk, Project
from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


def _parse_memory_list(raw: str) -> list:
    data = parse_json(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        mem = data.get("memory", [])
        return mem if isinstance(mem, list) else []
    return []


async def gen_memory(svc: Any, project: Project, ctx: dict):
    system = "你是小说设定记忆管理专家。只返回JSON数组。"
    char_snapshot = "、".join(
        f"{n}（{ctx.get('char_realms', {}).get(n, '未知境界')}）"
        for n in ctx.get("char_names", [])[:6]
    )
    prompt = f"""小说：《{ctx['project_title']}》主角：{ctx.get('protagonist', '主角')}
境界体系：{ctx.get('power_summary', '（未设定）')}
故事线：{ctx.get('storyline_summary', '（未设定）')}
主要人物：{char_snapshot or ctx.get('char_names', [])}
卷级结构：{ctx.get('volumes_summary', '（未设定）')}
设定摘要：{ctx['settings_summary'][:400]}

生成10条初始记忆库种子，覆盖「境界锚点、人物初始状态、故事线起点、关键设定规则、核心伏笔」五类，
作为后续写作的防矛盾基线，返回JSON数组：
[
  {{
    "memory_type": "setting",
    "title": "简短标题（10字内，精准可查）",
    "content": "具体内容，可直接作为写作参考（不少于30字）",
    "tags": ["分类标签"]
  }}
]
memory_type 只能是: event / character_state / foreshadow / setting / conflict"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=max_tokens_bootstrap_completion(),
        task="bootstrap.memory",
    )
    try:
        data = _parse_memory_list(raw)
    except json.JSONDecodeError as first_err:
        logger.warning("Bootstrap memory JSON parse failed, retrying: %s", first_err)
        raw = await svc._call_with_retry(
            system + " 上次输出不是合法 JSON。键名与字符串必须用英文双引号，禁止注释与尾逗号。",
            prompt + "\n\n【修正】只输出一个合法 JSON 数组，不要 markdown 代码块或任何说明文字。",
            max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.memory",
        )
        try:
            data = _parse_memory_list(raw)
        except json.JSONDecodeError as second_err:
            logger.error("Bootstrap memory JSON parse failed after retry: %s", second_err)
            raise second_err from first_err

    results = []
    for item in data:
        m = MemoryChunk(
            project_id=project.id,
            memory_type=item.get("memory_type", "setting"),
            title=item.get("title"),
            content=item.get("content", ""),
            tags=item.get("tags", []),
            chapter_number=0,
        )
        svc.db.add(m)
        results.append(m)

    svc.db.commit()

    try:
        from app.services.embedding_service import embed_texts as _embed_texts
        from app.models.memory import HAS_PGVECTOR
        if HAS_PGVECTOR and results:
            _texts = [(m, (m.title or "") + " " + (m.content or "")) for m in results]
            _vectors = await _embed_texts([t for _, t in _texts])
            for (m, _), vec in zip(_texts, _vectors):
                m.embedding = vec
            svc.db.commit()
    except Exception as _exc:
        logger.warning("Bootstrap memory embedding failed (non-fatal): %s", _exc)

    return results
