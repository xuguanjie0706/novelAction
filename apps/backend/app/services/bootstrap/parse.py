"""Bootstrap JSON / 数值容错解析层。

- `parse_json` 解析 LLM 返回的 JSON 文本，处理常见的「markdown fence / `<think>` 块 / 前置说明」干扰。
- `coerce_power_system_rank` 将 LLM 误填的境界中文名映射回 levels[].rank 整数。
- `safe_int` 允许字符串内嵌数字、float 等输入，统一裁剪到 [min_v, max_v]。

设计动机：所有 `_call_ai` 后的 JSON 解析必须经此处理（参见 CLAUDE.md「JSON 解析」），
避免在每个 step 文件里散落同形态 try/except。

向后兼容：旧 `services/generation_service.py` 顶部以 `_parse_json` / `_safe_int` /
`_coerce_power_system_rank` 别名重新导出，外部 import 路径不变。
"""

from __future__ import annotations

import json
import re
from typing import Any


def _extract_json_span(text: str) -> str:
    """截取最外层 JSON 片段（首个 {/[ 到末个 }/]），丢弃尾部说明文字。"""
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj == -1 and start_arr == -1:
        return text
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        start, end_char = start_arr, "]"
    else:
        start, end_char = start_obj, "}"
    end = text.rfind(end_char)
    if end != -1 and end >= start:
        return text[start : end + 1]
    return text[start:]


def _repair_llm_json_typos(text: str) -> str:
    """修复 LLM 偶发的结构性笔误（在 normalize 之前执行）。"""
    # 数组最后一项字符串误以 "] 收尾（应为 "），常见于 suggestions/issues
    text = re.sub(r'([^\\])"\](\s*\n\s*\],)', r'\1"\2', text)
    return text


def _normalize_json_text(text: str) -> str:
    """修复 LLM 常见非标准 JSON：智能引号、尾逗号、无引号键名、整行注释。"""
    for old, new in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
    ):
        text = text.replace(old, new)
    lines = []
    for line in text.split("\n"):
        if line.strip().startswith("//"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    text = re.sub(
        r'([{\[,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
        r'\1 "\2":',
        text,
    )
    return text


def parse_json(text: str) -> Any:
    """容错 JSON 解析：去 markdown fence、去 think 标签、修复常见 LLM 格式问题。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if fence:
        text = fence.group(1).strip()
    start = min(
        (text.find("{") if text.find("{") != -1 else len(text)),
        (text.find("[") if text.find("[") != -1 else len(text)),
    )
    text = text[start:]
    text = _extract_json_span(text)
    text = _repair_llm_json_typos(text)
    candidates = (text, _normalize_json_text(text))
    last_err: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_err = exc
            continue
    assert last_err is not None
    raise last_err


def coerce_power_system_rank(value, levels: list, default: int | None) -> int | None:
    """
    DB 列 protagonist_*_rank 为 Integer，须对应 levels[].rank。
    LLM 常误填境界中文名；此处尽量解析为整数，失败则回退 default。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return int(s)
        except ValueError:
            pass
        norm_levels = [lv for lv in (levels or []) if isinstance(lv, dict)]
        for lv in norm_levels:
            name = (lv.get("name") or "").strip()
            if not name:
                continue
            if s == name or name in s or s in name:
                r = lv.get("rank")
                if isinstance(r, int):
                    return r
                try:
                    return int(r)
                except (TypeError, ValueError):
                    continue
    return default


def safe_int(
    value,
    default: int | None = None,
    *,
    min_v: int | None = None,
    max_v: int | None = None,
) -> int | None:
    """
    单次生成 JSON 里 Integer 字段常被写成字符串或非数字文案；
    尽量解析为 int，失败则 default；可选 min/max 裁剪。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        out = value
    elif isinstance(value, float) and value == int(value):
        out = int(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            out = int(s)
        except ValueError:
            m = re.search(r"-?\d+", s)
            if not m:
                return default
            out = int(m.group(0))
    else:
        return default
    if min_v is not None:
        out = max(min_v, out)
    if max_v is not None:
        out = min(max_v, out)
    return out
