"""Bootstrap Step 9.5 / 9.8 共用：JSON 数组 LLM 调用、解析重试与 extra 落库。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)

_JSON_STRICT_SUFFIX = (
    " 禁止输出推理过程、Markdown 或任何说明文字。"
    "只返回一个合法 JSON 数组，键名与字符串必须用英文双引号。"
)


def _coerce_json_array(data: Any, task: str) -> list[dict]:
    if not isinstance(data, list):
        raise ValueError(f"{task} 返回非数组 JSON")
    return [row for row in data if isinstance(row, dict)]


async def call_json_array_with_retry(
    svc: Any,
    system: str,
    prompt: str,
    *,
    task: str,
) -> list[dict]:
    """调用 LLM 并解析 JSON 数组；解析失败时追加约束重试一次。"""
    max_tok = max_tokens_bootstrap_completion()
    raw = await svc._call_with_retry(system, prompt, max_tokens=max_tok, task=task)
    try:
        return _coerce_json_array(parse_json(raw), task)
    except (json.JSONDecodeError, ValueError) as first_err:
        logger.warning("%s JSON parse failed, retrying: %s", task, first_err)
        raw = await svc._call_with_retry(
            system + _JSON_STRICT_SUFFIX,
            prompt + "\n\n【修正】只输出合法 JSON 数组，不要 markdown 代码块或任何说明文字。",
            max_tokens=max_tok,
            task=task,
        )
        try:
            return _coerce_json_array(parse_json(raw), task)
        except (json.JSONDecodeError, ValueError) as second_err:
            logger.error("%s JSON parse failed after retry: %s", task, second_err)
            raise second_err from first_err


def persist_extra_arc(svc: Any, project: Any, key: str, arc: list[dict]) -> None:
    """将 arc 列表写入 ``Project.extra[key]`` 并提交。"""
    base = project.extra if isinstance(project.extra, dict) else {}
    project.extra = {**base, key: arc}
    flag_modified(project, "extra")
    svc.db.commit()
    svc.db.refresh(project)


def merge_project_extra_fields(svc: Any, project: Any, fields: dict[str, Any]) -> None:
    """一次性合并多个 extra 键，供并行步骤完成后统一落库。"""
    svc.db.refresh(project)
    base = dict(project.extra) if isinstance(project.extra, dict) else {}
    base.update(fields)
    project.extra = base
    flag_modified(project, "extra")
    svc.db.commit()
    svc.db.refresh(project)


async def call_json_object_with_retry(
    svc: Any,
    system: str,
    prompt: str,
    *,
    task: str,
) -> dict:
    """调用 LLM 并解析 JSON 对象；解析失败时追加约束重试一次。"""
    max_tok = max_tokens_bootstrap_completion()
    raw = await svc._call_with_retry(system, prompt, max_tokens=max_tok, task=task)
    try:
        data = parse_json(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{task} 返回非对象 JSON")
        return data
    except (json.JSONDecodeError, ValueError) as first_err:
        logger.warning("%s JSON parse failed, retrying: %s", task, first_err)
        raw = await svc._call_with_retry(
            system + _JSON_STRICT_SUFFIX,
            prompt + "\n\n【修正】只输出合法 JSON 对象，不要 markdown 代码块或任何说明文字。",
            max_tokens=max_tok,
            task=task,
        )
        data = parse_json(raw)
        if not isinstance(data, dict):
            raise ValueError(f"{task} 返回非对象 JSON")
        return data


def apply_ladder_boss_names(arc: list[dict], ladder: list[dict]) -> list[dict]:
    """将 villain_arc 各卷 villain_name 对齐 antagonist_ladder 登记名。"""
    if not ladder:
        return arc
    for i, row in enumerate(arc):
        vi = row.get("vol_index")
        try:
            idx = int(vi) if vi is not None else i
        except (TypeError, ValueError):
            idx = i
        entry = next((r for r in ladder if int(r.get("vol_index", -1)) == idx), None)
        if entry and entry.get("boss_name"):
            row["villain_name"] = entry["boss_name"]
    return arc


def write_emotion_arc_ctx(ctx: dict, arc: list[dict]) -> None:
    if not arc:
        return
    ctx["emotion_arc"] = arc
    parts = []
    for i, v in enumerate(arc):
        title = v.get("vol_title") or f"卷{v.get('vol_index', i)}"
        parts.append(f"{title}({v.get('net_balance', '?')},{v.get('dominant_emotion', '?')})")
    ctx["emotion_arc_summary"] = " | ".join(parts)


def write_villain_arc_ctx(ctx: dict, arc: list[dict]) -> None:
    if not arc:
        return
    ctx["villain_arc"] = arc
    parts = []
    for i, v in enumerate(arc):
        title = v.get("vol_title") or f"卷{v.get('vol_index', i)}"
        goal = (v.get("vol_goal") or "?")[:20]
        parts.append(f"{title}:{v.get('villain_name', '?')}→{goal}[{v.get('vol_result', '?')}]")
    ctx["villain_arc_summary"] = " | ".join(parts)
