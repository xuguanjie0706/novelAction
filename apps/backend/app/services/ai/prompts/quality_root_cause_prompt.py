"""质检根因分析 —— prompt 与根因分类常量。

设计动机：质检反复抓到同类低级错（境界偏差、前后不一致、凭空设定），但「为什么」无人归因。
本 prompt 让模型对每个低分项判定**根因落在管线哪一层**，并给出**改代码/prompt/采样档**的修复方向，
而不只是改正文。CATEGORY_FIX_HINTS 提供静态落点兜底——即使 LLM 失败也有代码层指针。
"""

from __future__ import annotations

import json
from typing import Any

# ── 根因分类（固定枚举，落库 root_cause_category）──────────────────────────
CATEGORIES: dict[str, str] = {
    "context_missing": "写章时该注入的设定/连续性账本/人物状态根本没进 prompt（信息没到模型面前）",
    "context_ignored": "信息已注入但模型在正文里没遵守（注入了被忽略，缺硬约束兜底）",
    "outline_planning_error": "章纲/卷骨架本身规划就错（如 power_milestone 与境界表冲突）",
    "setting_self_contradiction": "设定库自身互相矛盾（PowerSystem/Character 等记录打架）",
    "sampling_too_creative": "采样温度过高导致放飞/自相矛盾（draft.* 档位问题）",
    "prompt_constraint_gap": "对应生成环节 prompt 缺少该硬约束条款（该写禁止却没写）",
    "manuscript_slip": "纯正文笔误，与管线无关，改正文即可",
    "unknown": "证据不足，需人工复核",
}

# ── 各根因 → 代码/管线层修复落点（静态兜底，合并进 evidence）──────────────
CATEGORY_FIX_HINTS: dict[str, str] = {
    "context_missing": "services/ai/context_builder_continuity.py / context_assembler.py：确认该字段是否进入写章注入块",
    "context_ignored": "services/ai/draft_stream.py 严禁清单 + context_builder_continuity.py 硬约束：把该约束升级为显式「禁止…」条款",
    "outline_planning_error": "services/bootstrap/steps/vol_chapter_plans.py + 章纲 linter：修正规划期校验与节拍",
    "setting_self_contradiction": "Bootstrap Step 13 一致性扫描 / 对应设定表（PowerSystem/Character）：消解源头矛盾",
    "sampling_too_creative": "services/llm_task_profiles.py：下调对应 draft.* temperature 或加 frequency/presence penalty",
    "prompt_constraint_gap": "对应生成环节 prompt 文件：补一条与该问题对应的硬约束条款",
    "manuscript_slip": "无需改代码，走 quality_micro_patch 正文微调即可",
    "unknown": "证据不足，建议人工复核后再归类",
}

ROOT_CAUSE_SYSTEM = (
    "你是网络小说生成系统的架构诊断师。下面是某章质检抓到的若干低分项。"
    "你的任务不是改正文，而是判断每个问题的**根因落在生成管线哪一层**，"
    "并给出**改代码/prompt/采样配置**的修复方向。严格只返回 JSON，无任何多余文字。"
)


def _categories_doc() -> str:
    return "\n".join(f"- {k}：{v}" for k, v in CATEGORIES.items())


def build_root_cause_prompt(
    chapter_title: str,
    chapter_excerpt: str,
    system_knowledge_brief: str,
    draft_context_note: str,
    items: list[dict[str, Any]],
) -> str:
    """构造批量根因分析 prompt。

    Args:
        chapter_title: 章标题。
        chapter_excerpt: 章节正文摘录（用于核对问题是否真实存在）。
        system_knowledge_brief: 系统当前掌握的设定/人物状态/连续性（判断信息是否「本可注入」）。
        draft_context_note: 写章时上下文是否可考据的说明（best-effort）。
        items: 低分项列表，每项含 idx/item_kind/dimension/score/severity/problem_summary。
    """
    items_block = json.dumps(
        [
            {
                "idx": it["idx"],
                "kind": it["item_kind"],
                "dimension": it["dimension"],
                "score": it.get("score"),
                "problem": it["problem_summary"],
            }
            for it in items
        ],
        ensure_ascii=False,
        indent=2,
    )
    return f"""章节标题：{chapter_title}

【章节正文摘录】（核对问题是否属实）
{chapter_excerpt}

【系统当前掌握的设定 / 人物状态 / 连续性账本】
（用于判断：被违反的事实**本应**可被注入吗？若此处就缺/就矛盾 → 偏 context_missing / setting_self_contradiction；
 若此处明明有、正文却违反 → 偏 context_ignored / prompt_constraint_gap / sampling_too_creative）
{system_knowledge_brief}

【写章上下文可考据性】
{draft_context_note}

【待归因的低分项】
{items_block}

可选根因分类（root_cause_category 只能取以下之一）：
{_categories_doc()}

对每个低分项，按其 idx 输出：
- root_cause_category：上面枚举之一
- root_cause_detail：一句话说清「为什么会发生」（指出是哪条信息缺失/被忽略/规划错/设定矛盾）
- code_fix_suggestion：**代码/管线层**的具体修复方向（改哪个文件/prompt/采样档，或确认无需改代码）

仅返回 JSON：
{{
  "results": [
    {{"idx": 0, "root_cause_category": "context_ignored", "root_cause_detail": "...", "code_fix_suggestion": "..."}}
  ]
}}"""
