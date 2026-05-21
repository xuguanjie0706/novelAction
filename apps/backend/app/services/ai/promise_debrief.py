"""
读者承诺深度闭环辅助模块。

单独提取，不并入 debrief.py（已超硬上限 600 行），符合
「新 AI 能力走 services/ai/<capability>.py」架构约定。

提供三个公共函数：

- enrich_with_promise_ids
    将 auto_debrief 返回的 fulfilled_promise_texts 服务端精确匹配为
    ReaderPromise ID 列表，供前端提交 chapter_debrief 时直接使用，
    避免前端重复做模糊匹配。

- apply_fulfilled_by_ids
    根据 ID 列表批量将 ReaderPromise 标记为 fulfilled，幂等。

- apply_plan_promise_fulfillment
    Bootstrap Step 12.5 在 OutlineNode.extra.promise_fulfilled 中写入
    「本章计划兑现的承诺关键词」，但此前从未与 ReaderPromise.status 联动。
    本函数在章节复盘提交时读取该规划字段，对仍处于 open 状态的承诺做
    模糊匹配并标记为 fulfilled，连通「规划时承诺 → 运行时兑现」两层。

调用方不需 import 具体模型，函数内部延迟 import 避免循环依赖。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_NGRAM = 4


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _fuzzy_match(query: str, target: str) -> bool:
    """四元组模糊匹配，与 debrief_routes.chapter_debrief 保持一致语义。

    Args:
        query: AI 返回的已兑现承诺文本（可能含轻微改写）。
        target: DB 中存储的 ReaderPromise.promise_text。

    Returns:
        True 表示两者描述的是同一条承诺。
    """
    query = query.strip()
    target = target.strip()
    if not query or not target:
        return False
    if query in target or target[:20] in query:
        return True
    if len(query) >= _NGRAM:
        for i in range(len(query) - _NGRAM + 1):
            if query[i : i + _NGRAM] in target:
                return True
    return False


# ── 公共接口 ──────────────────────────────────────────────────────────────────

def enrich_with_promise_ids(
    fulfilled_texts: list[str],
    open_promises: list[dict],
) -> list[str]:
    """将 auto_debrief 的 fulfilled_promise_texts 解析为精确 ID 列表。

    服务端完成匹配，结果写入缓存，前端提交时直接带上 ID，
    不需要再次做文本模糊匹配，减少误判。

    Args:
        fulfilled_texts: AI 返回的已兑现承诺文本列表（可能含轻微改写）。
        open_promises: auto_debrief route 已加载的 open promise 字典列表，
            每项至少含 {"id": str, "promise_text": str}。

    Returns:
        去重后的 ReaderPromise.id 字符串列表。
    """
    if not fulfilled_texts or not open_promises:
        return []

    matched_ids: list[str] = []
    for text in fulfilled_texts:
        for p in open_promises:
            pid = (p.get("id") or "").strip()
            ptext = (p.get("promise_text") or "").strip()
            if pid and ptext and _fuzzy_match(text, ptext):
                if pid not in matched_ids:
                    matched_ids.append(pid)
                break  # 每条文本只匹配第一个命中的 promise
    return matched_ids


def apply_fulfilled_by_ids(
    db: "Session",
    project_id: str,
    chapter_id,
    chapter_sort_order: int,
    promise_ids: list[str],
) -> int:
    """根据 ID 列表批量将 ReaderPromise 标记为已兑现。

    幂等：只处理 status=open 的条目，已兑现/破裂的跳过。

    Args:
        db: 数据库会话（调用方管理事务，本函数不 commit）。
        project_id: 项目 ID，用于防止跨项目误写。
        chapter_id: 兑现章节 ID（写入 fulfilled_chapter_id）。
        chapter_sort_order: 兑现章节序号（写入 fulfilled_chapter_number）。
        promise_ids: ReaderPromise.id 字符串列表。

    Returns:
        实际更新条数。
    """
    if not promise_ids:
        return 0

    from app.models import ReaderPromise
    from uuid import UUID

    count = 0
    for pid in promise_ids:
        try:
            pid_uuid = UUID(str(pid))
        except Exception:
            continue
        rp = (
            db.query(ReaderPromise)
            .filter(
                ReaderPromise.id == pid_uuid,
                ReaderPromise.project_id == project_id,
                ReaderPromise.status == "open",
            )
            .first()
        )
        if not rp:
            continue
        rp.status = "fulfilled"
        rp.fulfilled_chapter_id = chapter_id
        rp.fulfilled_chapter_number = chapter_sort_order
        count += 1

    if count:
        logger.info(
            "promise_debrief.apply_by_ids: project=%s chapter_sort=%d fulfilled=%d",
            project_id,
            chapter_sort_order,
            count,
        )
    return count


def apply_plan_promise_fulfillment(
    db: "Session",
    project_id: str,
    chapter_id,
    chapter_sort_order: int,
    outline_node_id=None,
) -> int:
    """从章节 chapter_plan 节点的 extra.promise_fulfilled 兑现读者承诺。

    Bootstrap Step 12.5 在 OutlineNode.extra 写入 promise_fulfilled 字段，
    表示「本章计划兑现的承诺关键词」，但此前该字段仅供大纲 Linter 检查，
    从未与 ReaderPromise.status 联动。

    本函数在 chapter_debrief 提交时调用，读取 promise_fulfilled 并做模糊匹配，
    将命中的 open 承诺标记为 fulfilled。作为「规划层兜底」，补充 AI 检测可能
    遗漏的承诺兑现。

    幂等：只处理 status=open 的承诺，多次调用安全。

    Args:
        db: 数据库会话（调用方管理事务，本函数不 commit）。
        project_id: 项目 ID。
        chapter_id: 章节 ID（写入 fulfilled_chapter_id）。
        chapter_sort_order: 章节 sort_order（写入 fulfilled_chapter_number
            并用于回退查找 chapter_plan 节点）。
        outline_node_id: 章节关联的 OutlineNode.id（可选，若已知则跳过
            Chapter 查询；None 时回退按 sort_order 查找 chapter_plan）。

    Returns:
        本次新标记为 fulfilled 的承诺条数。
    """
    from app.models import OutlineNode, ReaderPromise

    # ── 定位 chapter_plan 节点 ────────────────────────────────────────────────
    plan_node: OutlineNode | None = None

    if outline_node_id is not None:
        try:
            from uuid import UUID as _UUID
            oid = _UUID(str(outline_node_id))
            plan_node = db.query(OutlineNode).filter(
                OutlineNode.id == oid,
            ).first()
        except Exception:
            pass

    if plan_node is None:
        # 回退：按 sort_order 找同项目 chapter_plan 节点
        plan_node = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.project_id == project_id,
                OutlineNode.node_type == "chapter_plan",
                OutlineNode.sort_order == chapter_sort_order,
            )
            .first()
        )

    if not plan_node:
        return 0

    pf_text = ((plan_node.extra or {}).get("promise_fulfilled") or "").strip()
    if not pf_text:
        return 0

    # ── 模糊匹配 open 承诺 ────────────────────────────────────────────────────
    open_promises = (
        db.query(ReaderPromise)
        .filter(
            ReaderPromise.project_id == project_id,
            ReaderPromise.status == "open",
        )
        .all()
    )
    count = 0
    for rp in open_promises:
        if _fuzzy_match(pf_text, rp.promise_text or ""):
            rp.status = "fulfilled"
            rp.fulfilled_chapter_id = chapter_id
            rp.fulfilled_chapter_number = chapter_sort_order
            count += 1

    if count:
        logger.info(
            "promise_debrief.apply_plan: project=%s chapter_sort=%d "
            "plan_node=%s pf_text=%r fulfilled=%d",
            project_id,
            chapter_sort_order,
            str(plan_node.id),
            pf_text[:60],
            count,
        )
    return count
