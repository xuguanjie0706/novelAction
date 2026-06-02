"""章纲 linter 勾选修复：上下文感知 AI 补丁 + 落库 + 自动 relint。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import OutlineNode
from app.routers.outline.helpers.expand_context import _outline_node_to_chapter_context
from app.routers.outline.helpers.revisions import _apply_outline_patch_to_node
from app.services.ai_service import AIService
from app.services.bootstrap.parse import parse_json
from app.services.outline_linter.gate import report_blocks_commit
from app.services.outline_linter.run import persist_linter_report, run_volume_linter
from app.services.outline_linter.rules_sequence import lint_semantic_duplicates
from app.services.outline_linter.helpers import chapter_from_node
from app.services.llm_token_budgets import min_completion_tokens

logger = logging.getLogger(__name__)

# rule_id → 优先修改字段（注入 prompt）
_RULE_TARGET_FIELDS: dict[str, list[str]] = {
    "CH-01": ["protagonist_want"],
    "CH-02": ["protagonist_obstacle"],
    "CH-03": ["protagonist_choice"],
    "CH-04": ["choice_cost"],
    "CH-05": ["opening_hook"],
    "CH-06": ["end_hook"],
    "CH-07": ["end_hook"],
    "CH-08": ["core_event"],
    "CH-09": ["villain_action"],
    "SEQ-01": ["opening_hook", "core_event"],
    "SEQ-07": ["opening_hook"],
}

_PATCH_FIELD_KEYS = (
    "opening_hook",
    "core_event",
    "character_change",
    "foreshadow",
    "end_hook",
    "choice_cost",
    "protagonist_want",
    "protagonist_obstacle",
    "protagonist_choice",
    "villain_action",
)


def _format_chapter_block(ch: dict, *, label: str = "") -> str:
    prefix = f"{label} " if label else ""
    parts = [
        f"{prefix}第{ch.get('number', '?')}章《{ch.get('title', '')}》",
        f"开篇：{ch.get('opening_hook', '')}",
        f"核心：{ch.get('core_event', '')}",
        f"变化：{ch.get('character_change', '')}",
        f"选择：{ch.get('protagonist_choice', '')}",
        f"代价：{ch.get('choice_cost', '')}",
        f"章末：{ch.get('end_hook', '')}",
    ]
    return " | ".join(parts)


def build_linter_fix_prompt(
    *,
    project_title: str,
    genre: str,
    selected_pairs: list[tuple[int, dict]],
    chapters_by_number: dict[int, dict],
    positioning_context: str = "",
    user_prompt: str = "",
) -> tuple[str, str]:
    """构建 linter 定向修复 prompt（含前后章上下文）。"""
    issue_blocks: list[str] = []
    for seq, (issue_idx, iss) in enumerate(selected_pairs):
        ch_num = iss.get("chapter_number_in_volume")
        ch_num_int = ch_num if isinstance(ch_num, int) else None
        rule_id = str(iss.get("rule_id") or "")
        targets = _RULE_TARGET_FIELDS.get(rule_id, ["choice_cost", "opening_hook", "core_event"])
        ctx_lines: list[str] = []
        if ch_num_int is not None:
            for offset in (-1, 0, 1):
                neighbor = chapters_by_number.get(ch_num_int + offset)
                if neighbor:
                    tag = { -1: "[上章]", 0: "[本章]", 1: "[下章]" }.get(offset, "")
                    ctx_lines.append(_format_chapter_block(neighbor, label=tag))
        issue_blocks.append(
            f"[issue_seq={seq} issue_index={issue_idx}] rule={rule_id} "
            f"severity={iss.get('severity', '')}\n"
            f"  问题：{iss.get('message', '')}\n"
            f"  建议：{iss.get('suggestion', '')}\n"
            f"  优先改字段：{', '.join(targets)}\n"
            + ("\n".join(f"  {ln}" for ln in ctx_lines) if ctx_lines else "  （无章节上下文）")
        )

    user_note = f"\n用户补充方向：{user_prompt.strip()}\n" if user_prompt.strip() else ""
    positioning_block = (
        f"\n【立项定位约束】\n{positioning_context[:1200]}\n"
        if positioning_context.strip()
        else ""
    )

    system = (
        "你是资深网文大纲总编辑。用户勾选了章纲 linter 问题，请给出可落库的字段级补丁。"
        "只输出 JSON，不要 markdown。"
    )
    prompt = f"""小说：《{project_title}》（{genre}）
{positioning_block}
【勾选的问题（issue_seq 对应下方 patches 的 issue_seq）】
{chr(10).join(issue_blocks)}
{user_note}
修复要求：
1. 像总编辑改稿：结合上章代价/下章承接，给出具体叙事内容，不要写「待定」「悬念丛生」等占位。
2. CH-04/SEQ-01/SEQ-07 必须让 choice_cost 与 opening_hook 形成可见因果链（下章开篇须承接上章代价关键词或后果）。
3. 每个 patch 只改必要字段；未列出的字段不要输出。
4. 字段必须是可直接替换的短文本（每条 15～80 字为宜）。

返回 JSON：
{{
  "summary": "本轮修复概述",
  "patches": [
    {{
      "issue_seq": 0,
      "chapter_number": 7,
      "fields": {{
        "choice_cost": "…",
        "opening_hook": "…"
      }},
      "reason": "为何这样改（一句话）"
    }}
  ]
}}

fields 白名单：{", ".join(_PATCH_FIELD_KEYS)}"""
    return system, prompt


async def generate_linter_fix_patches(
    ai: AIService,
    *,
    project_title: str,
    genre: str,
    selected_pairs: list[tuple[int, dict]],
    chapters_by_number: dict[int, dict],
    positioning_context: str = "",
    user_prompt: str = "",
) -> dict[str, Any]:
    """调用 AI 生成 linter 修复补丁。"""
    if not selected_pairs:
        return {"summary": "未选择问题", "patches": []}

    system, prompt = build_linter_fix_prompt(
        project_title=project_title,
        genre=genre,
        selected_pairs=selected_pairs,
        chapters_by_number=chapters_by_number,
        positioning_context=positioning_context,
        user_prompt=user_prompt,
    )
    try:
        response = await ai._call_ai(
            system,
            prompt,
            max_tokens=min_completion_tokens(),
            context={"operation": "linter_fix", "issue_count": len(selected_pairs)},
            task="outline.repair",
        )
        text = response.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if "```" in text:
            fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if fence:
                text = fence.group(1).strip()
        data = parse_json(text)
        if not isinstance(data, dict):
            raise ValueError("响应不是 JSON 对象")
        patches = data.get("patches")
        if not isinstance(patches, list):
            data["patches"] = []
        return data
    except Exception as exc:
        logger.exception("linter_fix AI 调用失败")
        return {"error": str(exc), "patches": [], "summary": ""}


def apply_linter_fix_patches(
    db: Session,
    project_id: str,
    volume_node: OutlineNode,
    patches: list[dict],
    *,
    selected_pairs: list[tuple[int, dict]],
) -> tuple[list[dict], list[dict]]:
    """应用 AI 补丁，返回 (applied, skipped)。"""
    nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project_id,
            OutlineNode.parent_id == volume_node.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .all()
    )
    node_by_number = {
        _outline_node_to_chapter_context(n)["number"]: n
        for n in nodes
        if isinstance(_outline_node_to_chapter_context(n).get("number"), int)
    }

    applied: list[dict] = []
    skipped: list[dict] = []
    seen_issue_seq: set[int] = set()

    for raw in patches:
        if not isinstance(raw, dict):
            continue
        issue_seq = raw.get("issue_seq")
        ch_num = raw.get("chapter_number")
        fields = raw.get("fields")
        if not isinstance(fields, dict) or not isinstance(ch_num, int):
            if isinstance(issue_seq, int):
                skipped.append({
                    "issue_index": selected_pairs[issue_seq][0] if issue_seq < len(selected_pairs) else -1,
                    "reason": "补丁缺少 chapter_number 或 fields",
                    "suggestion": "请重试或手动编辑章纲",
                })
            continue

        node = node_by_number.get(ch_num)
        if not node:
            idx = selected_pairs[issue_seq][0] if isinstance(issue_seq, int) and issue_seq < len(selected_pairs) else -1
            skipped.append({
                "issue_index": idx,
                "reason": f"找不到第{ch_num}章节点",
                "suggestion": "",
            })
            continue

        record = _apply_outline_patch_to_node(node, raw)
        if not record.get("fields_changed"):
            idx = selected_pairs[issue_seq][0] if isinstance(issue_seq, int) and issue_seq < len(selected_pairs) else -1
            skipped.append({
                "issue_index": idx,
                "reason": "补丁未产生有效字段变更",
                "suggestion": str(raw.get("reason") or ""),
            })
            continue

        db.add(node)
        issue_idx = -1
        rule_id = ""
        if isinstance(issue_seq, int) and issue_seq < len(selected_pairs):
            issue_idx = selected_pairs[issue_seq][0]
            rule_id = str(selected_pairs[issue_seq][1].get("rule_id") or "")
            seen_issue_seq.add(issue_seq)

        applied.append({
            "issue_index": issue_idx,
            "chapter_number": ch_num,
            "rule_id": rule_id,
            "fields_changed": record.get("fields_changed") or [],
            "reason": record.get("reason") or raw.get("reason") or "",
            "applied": True,
        })

    db.commit()
    return applied, skipped


def relint_volume_and_update_block_state(
    db: Session,
    project: Any,
    volume_node: OutlineNode,
) -> dict[str, Any]:
    """修复后重跑 linter，通过则清除 linter_blocked / linter_hold。"""
    from sqlalchemy.orm.attributes import flag_modified

    report = run_volume_linter(db, project, volume_node)
    nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == volume_node.id,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )
    snaps = [chapter_from_node(n) for n in nodes]
    report.issues.extend(lint_semantic_duplicates(snaps))
    report.finalize_status()

    blocked = report_blocks_commit(report)
    persist_linter_report(volume_node, report)
    extra = dict(volume_node.extra or {})

    if blocked:
        extra["linter_blocked"] = True
        for node in nodes:
            node_extra = dict(node.extra or {})
            node_extra["linter_hold"] = True
            node.extra = node_extra
            flag_modified(node, "extra")
            db.add(node)
    else:
        extra.pop("linter_blocked", None)
        extra.pop("linter_block_reason", None)
        extra.pop("linter_user_message", None)
        for node in nodes:
            node_extra = dict(node.extra or {})
            if node_extra.pop("linter_hold", None) is not None:
                node.extra = node_extra
                flag_modified(node, "extra")
                db.add(node)

    volume_node.extra = extra
    flag_modified(volume_node, "extra")
    db.commit()

    return {
        "linter_status": report.status,
        "linter_blocked": blocked,
        "linter_report": report.to_dict(),
        "issue_count": len(report.issues),
        "critical_count": report.critical_count,
    }
