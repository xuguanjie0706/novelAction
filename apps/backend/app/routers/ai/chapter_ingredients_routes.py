"""
chapter_ingredients_routes.py — 本章投料清单 HTTP 端点

资源边界：
  本模块仅暴露一个端点：POST /ai/chapter-ingredients
  负责计算并返回结构化投料清单（ChapterIngredients），同时持久化到
  OutlineNode.extra.pre_write_constraints。

  该端点同时服务于：
  1. 写前预警面板（前端展示债务看板 / 约束摘要）
  2. 分场生成（scene_routes 在 plan-save 时调用此服务取约束块）

端点：
  POST /projects/{project_id}/ai/chapter-ingredients
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, OutlineNode, Project
from app.services.ai.chapter_ingredients import (
    ChapterIngredients,
    build_constraints_prompt_block,
    compute_chapter_ingredients,
)

router = APIRouter()


class ChapterIngredientsRequest(BaseModel):
    """
    投料清单计算请求。

    Args:
        outline_node_id: chapter_plan 节点 UUID（必填）。
        chapter_id: 可选，用于读取章节序号（sort_order）。
        chapter_number: 可选，直接指定章节序号（优先于 chapter_id 中读取）。
    """
    outline_node_id: UUID
    chapter_id: Optional[UUID] = None
    chapter_number: Optional[int] = None


@router.post("/chapter-ingredients")
async def get_chapter_ingredients(
    project_id: str,
    req: ChapterIngredientsRequest,
    db: Session = Depends(get_db),
):
    """
    计算并返回本章投料清单（ChapterIngredients）。

    纯 DB 计算，不调用 LLM，速度快（< 500ms）。
    同时将结构化结果持久化到 OutlineNode.extra.pre_write_constraints。

    Returns:
        {
          "structured": {ChapterIngredients JSON},   # 供分场 AI 注入
          "prompt_block": str,                        # 格式化约束文本，可直接注入 prompt
          "debt_summary": {                           # 供前端债务看板展示
            "critical_count": int,
            "warning_count": int,
            "must_advance_storylines": [...],
            "overdue_foreshadows": [...],
            "due_promises": [...],
          }
        }

    Raises:
        404: project 或 outline_node 不存在。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    node = db.query(OutlineNode).filter(
        OutlineNode.id == req.outline_node_id,
        OutlineNode.project_id == project_id,
    ).first()
    if not node:
        raise HTTPException(404, "OutlineNode not found")

    # 解析章节序号
    chapter_number = req.chapter_number or 0
    if not chapter_number and req.chapter_id:
        ch = db.query(Chapter).filter(
            Chapter.id == req.chapter_id,
            Chapter.project_id == project_id,
        ).first()
        if ch:
            chapter_number = ch.sort_order or 0
    if not chapter_number and node.sort_order:
        chapter_number = node.sort_order

    # 计算投料清单
    ingredients: ChapterIngredients = await compute_chapter_ingredients(
        db=db,
        project_id=project_id,
        outline_node_id=str(req.outline_node_id),
        chapter_number=chapter_number,
    )

    # 格式化约束文本块（供调用方直接拼入 prompt）
    prompt_block = build_constraints_prompt_block(ingredients)

    # 前端债务看板摘要
    critical_count = sum(1 for d in ingredients.debt_flags if d.severity == "critical")
    warning_count = sum(1 for d in ingredients.debt_flags if d.severity == "warning")

    debt_summary = {
        "critical_count": critical_count,
        "warning_count": warning_count,
        "total_debt_count": len(ingredients.debt_flags),
        "must_advance_storylines": [
            {"name": m.name, "line_type": m.line_type, "gap_chapters": m.gap_chapters}
            for m in ingredients.storyline_moves
            if m.must_advance
        ],
        "overdue_foreshadows": [
            {"title": op.title, "op": op.op, "is_overdue": op.is_overdue}
            for op in ingredients.foreshadow_ops
            if op.is_overdue or op.op == "resolve"
        ],
        "due_promises": [
            {"description": d.description}
            for d in ingredients.debt_flags
            if d.debt_type == "promise_due"
        ],
        "debt_flags": [
            {
                "debt_type": d.debt_type,
                "description": d.description,
                "severity": d.severity,
                "overdue_chapters": d.overdue_chapters,
            }
            for d in ingredients.debt_flags
        ],
    }

    return {
        "structured": ingredients.to_dict(),
        "prompt_block": prompt_block,
        "debt_summary": debt_summary,
    }
