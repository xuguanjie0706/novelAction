"""修仙线合并步骤：核心谜题 + 开局追读承诺一次 LLM 生成。

把通用线两步（core_mysteries / opening_contract）并成一次调用（-1 LLM）。

为何不直接套用番茄 promise_seeds
------------------------------
番茄 promise_seeds 用的是番茄专属的 opening_contract schema；而修仙线沿用**通用
schema**，那正是「无事实承诺」改造 + 卷级 Boss 归属表（OC-LADDER）所在，下游
（build_opening_contract_expand_block / 里程碑播种 / OC-LADDER）都按通用 schema 取值。
故本节点**复用 CORE 的 build_opening_contract_prompt 与 finalize_opening_contract**，
让那套约束与持久化只有一处、不随合并漂移；core_mysteries 同理复用 CORE 构造/落库。

健壮性：合并响应缺哪部分，就回退到对应的独立步骤补齐——最坏退化为今天的两次调用，
绝不产出更差结果。

红线：本文件 ≤ 600 行。
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.steps.core_mysteries import (
    build_core_mysteries_prompt,
    persist_core_mysteries,
    set_core_mysteries_ctx,
)
from app.services.bootstrap.steps.opening_contract import (
    _load_vol1_node,
    finalize_opening_contract,
)
from app.services.bootstrap.prompts.opening_contract import build_opening_contract_prompt
from app.services.llm_token_budgets import max_tokens_bootstrap_completion

logger = logging.getLogger(__name__)


def _build_merged_prompt(project: Project, ctx: dict, vol1) -> tuple[str, str]:
    """把 CORE 的谜题 prompt 与 开局承诺 prompt 包成一次「合并返回」调用。"""
    _, cm_prompt = build_core_mysteries_prompt(ctx)
    _, oc_prompt = build_opening_contract_prompt(project, ctx, vol1=vol1)

    system = (
        "你是有30年经验的网络小说总编辑，一次性完成两项开局规划并合并返回。"
        "忽略下面两个子任务各自结尾「只返回JSON」的措辞，以最外层合并结构为准。"
        "只返回一个 JSON 对象，不要任何解释文字。"
    )
    prompt = f"""你要一次完成两项规划，最终合并为**一个 JSON 对象**返回。

═══════════ 子任务一：核心谜题（输出到键 "core_mysteries"，值是数组）═══════════
{cm_prompt}

═══════════ 子任务二：开局追读承诺（输出到键 "opening_contract"，值是对象）═══════════
{oc_prompt}

═══════════ 合并返回（最高优先级，覆盖以上两段的「只返回」措辞）═══════════
只返回如下结构，不要任何解释：
{{"core_mysteries": <子任务一的 JSON 数组>, "opening_contract": <子任务二的 JSON 对象>}}
两个子任务要彼此呼应：开局承诺里埋的悬念应与某条核心谜题的 lay 锚点一致。"""
    return system, prompt


async def gen_promise_seeds_xianxia(svc: Any, project: Project, ctx: dict) -> dict:
    """一次生成核心谜题 + 开局承诺，分别落库；缺失部分回退原步骤。

    Returns:
        dict 含 core_mysteries 列表 + opening_contract 字典（供 _fanqie_step 判定 ok）。
    """
    vol1 = _load_vol1_node(svc, project)
    genre = ctx.get("genre", project.genre or "玄幻")
    system, prompt = _build_merged_prompt(project, ctx, vol1)

    data: Any = {}
    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=max_tokens_bootstrap_completion(),
            task="bootstrap.opening_contract",
        )
        data = parse_json(raw)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}

    mysteries = data.get("core_mysteries")
    mysteries = mysteries if isinstance(mysteries, list) else []
    contract = data.get("opening_contract")
    contract = contract if isinstance(contract, dict) else {}

    # ── A. 核心谜题（缺失则回退独立步骤）────────────────────────────────────
    if mysteries:
        persist_core_mysteries(svc, project, mysteries)
        set_core_mysteries_ctx(ctx, mysteries)
    else:
        logger.warning(
            "promise_seeds_xianxia 合并响应缺 core_mysteries，回退独立步骤 project=%s",
            project.id,
        )
        from app.services.bootstrap.steps.core_mysteries import gen_core_mysteries
        mysteries = await gen_core_mysteries(svc, project, ctx)

    # ── B. 开局承诺（缺失则回退独立步骤）────────────────────────────────────
    if contract:
        finalize_opening_contract(svc, project, ctx, contract, genre)
    else:
        logger.warning(
            "promise_seeds_xianxia 合并响应缺 opening_contract，回退独立步骤 project=%s",
            project.id,
        )
        from app.services.bootstrap.steps.opening_contract import gen_opening_contract
        contract = await gen_opening_contract(svc, project, ctx)

    logger.info(
        "bootstrap.promise_seeds_xianxia 完成 project=%s 谜题=%d 承诺字段=%d",
        project.id, len(mysteries), len(contract or {}),
    )
    return {"core_mysteries": mysteries, "opening_contract": contract}
