"""linter 问题回灌 → 定向重写闭环（每批一轮，可配 repair_rounds）。

设计：批生成 → lint 本批（逐章规则 + 批内同质化）→ 有问题则把 issues + 原章 +
相邻章喂回 LLM，只重写问题章 → 按 chapter_number 合并回原批。

边界约定：
  - REALM-* 不进修复：境界由 steps._enforce_realm 写库前硬保证，修复章的
    realm_rank 强制还原为原值（修复不许动境界脊柱）。
  - DB-02（黄金三章）仅当本批含全书第 1 章时生效（lint_chapters 按位置取前 3 章，
    中段批误报需过滤）；DB-08（大爆点）在小尾批（< big_beat_every 章）跳过。
  - 修复失败 / 返回空数组 → 保留原批（修复是增益，不是阻断）。
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from dabai import linter, schemas
from dabai.config import DabaiConfig

logger = logging.getLogger("dabai.repair")

CallFn = Callable[[str, str, str, dict | None], Awaitable[Any]]


def _batch_issues(
    report: linter.LinterReport, batch: list[dict], cfg: DabaiConfig,
) -> list[linter.Issue]:
    """过滤出本批可定向修复的问题（去掉境界类与中段批误报）。"""
    first_num = int(batch[0].get("chapter_number") or 0) if batch else 0
    out: list[linter.Issue] = []
    for issue in report.issues:
        if issue.rule_id.startswith("REALM"):
            continue  # 境界由写库前硬保证兜底
        if issue.rule_id == "DB-02" and first_num != 1:
            continue  # 黄金三章只看全书开局批
        if issue.rule_id == "DB-08" and len(batch) < cfg.big_beat_every:
            continue  # 小尾批不强求大爆点
        out.append(issue)
    return out


def _neighbors_of(work: list[dict], nums: set[int]) -> list[dict]:
    """问题章的相邻合格章（供修复时满足轮换规则，本身不重写）。"""
    out = []
    for ch in work:
        n = int(ch.get("chapter_number") or 0)
        if n not in nums and ((n - 1) in nums or (n + 1) in nums):
            out.append({
                "chapter_number": n, "title": ch.get("title"),
                "location": ch.get("location"), "shuang_type": ch.get("shuang_type"),
            })
    return out


async def repair_batch(
    ctx: dict, call: CallFn, cfg: DabaiConfig, batch: list[dict], *,
    realm_range: tuple[int | None, int | None] | None = None,
    realm_max: int | None = None,
    golden_finger_name: str = "",
) -> list[dict]:
    """对一批章纲跑 lint→定向重写，返回修复后的批（失败原样返回）。"""
    if cfg.repair_rounds <= 0 or not batch:
        return batch
    from dabai import prompts  # 延迟导入：steps→repair→prompts 不与 steps→prompts 成环

    work = batch
    for round_no in range(cfg.repair_rounds):
        report = linter.lint_chapters(
            work, cfg, realm_max=realm_max, realm_range=realm_range,
            golden_finger_name=golden_finger_name,
            ctx=ctx,
        )
        issues = _batch_issues(report, work, cfg)
        if not issues:
            return work
        nums = sorted({i.chapter for i in issues if i.chapter})
        if any(i.chapter is None for i in issues):
            # 卷级问题（同质化/缺大爆点/黄金三章）：整批进待修，让模型全局调配
            nums = [int(ch.get("chapter_number") or 0) for ch in work]
        nums_set = set(nums)
        problem = [ch for ch in work if int(ch.get("chapter_number") or 0) in nums_set]
        if not problem:
            return work

        ctx["_repair"] = {
            "chapters": problem,
            "issues": [i.as_dict() for i in issues],
            "neighbors": _neighbors_of(work, nums_set),
        }
        try:
            system, user = prompts.build("chapter_repair", ctx, cfg)
            raw = await call("chapter_repair", system, user, {"chapters": nums})
        except Exception as exc:  # noqa: BLE001
            logger.warning("章纲修复调用失败(round=%d)，保留原批：%s", round_no + 1, exc)
            break
        finally:
            ctx.pop("_repair", None)

        fixed = schemas.normalize_step(
            "chapter_repair", raw if isinstance(raw, list) else [])
        if not fixed:
            logger.info("章纲修复返回空，保留原批（问题 %d 条）", len(issues))
            break
        by_num = {int(ch.get("chapter_number") or 0): ch for ch in work}
        applied = 0
        for f in fixed:
            n = int(f.get("chapter_number") or 0)
            if n in by_num and n in nums_set:
                f["realm_rank"] = by_num[n].get("realm_rank")  # 修复不许改境界
                by_num[n] = f
                applied += 1
        if applied:
            work = [by_num[int(ch.get("chapter_number") or 0)] for ch in work]
            logger.info("章纲修复 round=%d 应用 %d/%d 章（问题 %d 条）",
                        round_no + 1, applied, len(problem), len(issues))
        else:
            break
    return work
