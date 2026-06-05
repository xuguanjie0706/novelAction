"""章纲伏笔结构化 ops：解析、校验、与 legacy 文本 DSL 互转。

真源优先 ``foreshadow_ops`` JSON 数组；``extra.foreshadow`` 文本仅作展示与存量兼容。
"""
from __future__ import annotations

import re
from typing import Any

_VALID_OPS = frozenset({"lay", "heat", "resolve"})

# legacy 文本 DSL（与 foreshadow_sync 历史 prompt 一致）
_BRACKET_OPEN = r"[\[【＜]"
_BRACKET_CLOSE = r"[)\]＞】]"
_RE_LAY = re.compile(rf"埋{_BRACKET_OPEN}(.+?){_BRACKET_CLOSE}", re.UNICODE)
_RE_HEAT = re.compile(rf"加热{_BRACKET_OPEN}(.+?){_BRACKET_CLOSE}", re.UNICODE)
_RE_RESOLVE = re.compile(rf"收{_BRACKET_OPEN}(.+?){_BRACKET_CLOSE}", re.UNICODE)
_RE_THEME = re.compile(r"^(.+?)\|主题[:：](.+)$")


def _parse_lay_body(raw: str) -> tuple[str, str]:
    """从 '伏笔内容|主题:关联' 解析 (name, theme)。"""
    m = _RE_THEME.match((raw or "").strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (raw or "").strip(), ""


def normalize_op(raw: Any) -> dict[str, Any] | None:
    """校验单条 foreshadow_op；非法条目返回 None。"""
    if not isinstance(raw, dict):
        return None
    op = str(raw.get("op") or "").strip().lower()
    if op not in _VALID_OPS:
        return None

    code = str(raw.get("code") or "").strip() or None
    name = str(raw.get("name") or "").strip()
    theme = str(raw.get("theme") or "").strip()
    note = str(raw.get("note") or raw.get("detail") or "").strip()

    if op == "lay":
        if not name:
            return None
        out: dict[str, Any] = {"op": "lay", "name": name}
        if theme:
            out["theme"] = theme
        return out

    # heat / resolve：code 或 note 至少其一
    if not code and not note and not name:
        return None
    out = {"op": op}
    if code:
        out["code"] = code
    if name:
        out["name"] = name
    if note:
        out["note"] = note
    return out


def legacy_string_to_ops(raw: str) -> list[dict[str, Any]]:
    """将 ``埋[…]/加热[…]/收[…]`` 文本转为结构化 ops。"""
    text = (raw or "").strip()
    if not text:
        return []

    ops: list[dict[str, Any]] = []
    for m in _RE_LAY.finditer(text):
        name, theme = _parse_lay_body(m.group(1))
        if not name:
            continue
        op: dict[str, Any] = {"op": "lay", "name": name}
        if theme:
            op["theme"] = theme
        ops.append(op)

    for m in _RE_HEAT.finditer(text):
        note = m.group(1).strip()
        if note:
            ops.append({"op": "heat", "note": note})

    for m in _RE_RESOLVE.finditer(text):
        note = m.group(1).strip()
        if note:
            ops.append({"op": "resolve", "note": note})

    return ops


def ops_to_legacy_string(ops: list[dict[str, Any]]) -> str:
    """结构化 ops → 人类可读 legacy 串（UI / linter 子串兼容）。"""
    parts: list[str] = []
    for raw in ops or []:
        op = normalize_op(raw)
        if not op:
            continue
        kind = op["op"]
        if kind == "lay":
            body = op["name"]
            if op.get("theme"):
                body = f"{body}|主题:{op['theme']}"
            parts.append(f"埋[{body}]")
        elif kind == "heat":
            label = op.get("code") or op.get("note") or op.get("name") or ""
            if label:
                parts.append(f"加热[{label}]")
        elif kind == "resolve":
            label = op.get("code") or op.get("note") or op.get("name") or ""
            if label:
                parts.append(f"收[{label}]")
    return " ".join(parts)


def coerce_foreshadow_ops(item: dict[str, Any]) -> list[dict[str, Any]]:
    """从章纲 JSON 条目提取 ops：优先 foreshadow_ops，回退 legacy foreshadow 文本。"""
    raw_ops = item.get("foreshadow_ops")
    if isinstance(raw_ops, list) and raw_ops:
        normalized = [o for o in (normalize_op(x) for x in raw_ops) if o]
        if normalized:
            return normalized

    legacy = (item.get("foreshadow") or "").strip()
    if legacy:
        return legacy_string_to_ops(legacy)
    return []


def apply_chapter_foreshadow_fields(item: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """
    章纲落库用：返回 (foreshadow_ops, foreshadow_legacy_str)。

    legacy 串由 ops 渲染，保证 extra 双写字段一致。
    """
    ops = coerce_foreshadow_ops(item)
    legacy = ops_to_legacy_string(ops) if ops else (item.get("foreshadow") or "").strip()
    return ops, legacy


def ops_to_node_columns(
    ops: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """映射到 OutlineNode.foreshadows_laid / foreshadows_resolved。"""
    laid: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for raw in ops or []:
        op = normalize_op(raw)
        if not op:
            continue
        if op["op"] == "lay":
            entry: dict[str, Any] = {
                "id": op.get("code") or op["name"],
                "description": op["name"],
            }
            if op.get("theme"):
                entry["theme"] = op["theme"]
            laid.append(entry)
        elif op["op"] == "resolve":
            resolved.append({
                "id": op.get("code") or op.get("note") or op.get("name") or "",
                "description": op.get("note") or op.get("name") or "",
            })
    return laid, resolved


def chapter_has_lay(ops: list[dict[str, Any]] | None) -> bool:
    """本章是否含埋伏笔 op。"""
    return any(
        isinstance(o, dict) and str(o.get("op") or "").lower() == "lay"
        for o in (ops or [])
    )


def extract_lay_names(ops: list[dict[str, Any]] | None) -> list[str]:
    """提取本章埋伏笔名称列表（日程冲突检测 / linter）。"""
    names: list[str] = []
    for raw in ops or []:
        op = normalize_op(raw)
        if op and op["op"] == "lay" and op.get("name"):
            names.append(op["name"])
    return names


def prepare_chapter_foreshadow_for_node(
    item: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    """章纲落库：ops、foreshadows_laid、foreshadows_resolved、legacy 展示串。"""
    ops, legacy = apply_chapter_foreshadow_fields(item)
    laid, resolved = ops_to_node_columns(ops)
    return ops, laid, resolved, legacy


def _ops_from_extra(extra: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(extra, dict):
        return []
    raw_ops = extra.get("foreshadow_ops")
    if isinstance(raw_ops, list) and raw_ops:
        return [o for o in (normalize_op(x) for x in raw_ops) if o]
    legacy = (extra.get("foreshadow") or "").strip()
    return legacy_string_to_ops(legacy) if legacy else []


def foreshadow_summary_from_extra(extra: dict[str, Any] | None) -> str:
    """审计 / prompt / 跨卷上下文用摘要（ops 优先，回退 legacy 文本）。"""
    ops = _ops_from_extra(extra)
    if ops:
        return ops_to_legacy_string(ops)
    if isinstance(extra, dict):
        return (extra.get("foreshadow") or "").strip()
    return ""


def _name_overlap(a: str, b: str) -> bool:
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    return a in b or b in a


def mystery_op_covered(name: str, extra: dict[str, Any] | None, op_kind: str) -> bool:
    """
    核心谜题 name 是否已在章纲 ops（或 legacy 文本）中体现 lay/heat/resolve。

    Args:
        op_kind: ``lay`` | ``heat`` | ``resolve``
    """
    if not (name or "").strip():
        return False
    name = name.strip()
    for op in _ops_from_extra(extra):
        if op.get("op") != op_kind:
            continue
        if op_kind == "lay":
            if _name_overlap(name, op.get("name") or ""):
                return True
            continue
        ref = " ".join(
            x for x in (op.get("code"), op.get("note"), op.get("name")) if x
        )
        if _name_overlap(name, ref):
            return True

    legacy = foreshadow_summary_from_extra(extra if isinstance(extra, dict) else {})
    if not legacy:
        return False
    if op_kind == "lay":
        return _name_overlap(name, legacy) and "埋[" in legacy
    if op_kind == "heat":
        return _name_overlap(name, legacy) and "加热[" in legacy
    return _name_overlap(name, legacy) and "收[" in legacy
