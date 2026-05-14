"""大纲专项质检聚合接口。

三个专项质检（因果链 / 人物弧 / 伏笔审计）并行执行，返回聚合报告。
各检查只专注单一维度，比全局质检有更高的精准度。

使用场景：
- Bootstrap 完成后对第一卷章纲做快速诊断
- 用户手动触发某卷的质检（前端「质检」按钮）
- 全量大纲生成完毕后的后置校验
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Character, OutlineNode, Project
from app.services.ai_service import AIService

router = APIRouter()


class OutlineChecksRequest(BaseModel):
    """专项质检请求体。"""
    node_id: str                          # 待检卷/篇节点 UUID
    model_profile: str = "default"        # AI 线路（default / gemini）
    llm_provider_id: Optional[str] = None # 管理后台 LlmProvider UUID


class CheckSummary(BaseModel):
    """聚合质检结果概要。"""
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    checks_passed: list[str]   # 通过的检查项名称
    checks_warned: list[str]   # 有问题的检查项名称


@router.post("/ai-checks/outline")
async def outline_checks_aggregate(
    project_id: str,
    req: OutlineChecksRequest,
    db: Session = Depends(get_db),
):
    """并行运行三个专项大纲质检，返回聚合报告。

    三个子检查：
    - **causality**：章节间因果链（上章代价是否驱动本章事件）
    - **character_arc**：主角弧度（欲望/选择/代价的连贯性）
    - **foreshadow**：伏笔审计（埋/收配对 + 主题共鸣质量）

    Args:
        project_id: 项目 UUID（路径参数）。
        req: 请求体，含待检节点 ID 和模型配置。

    Returns:
        JSON 格式聚合报告：
        {
          "causality": {...},       # 因果链检查结果
          "character_arc": {...},   # 人物弧检查结果
          "foreshadow": {...},      # 伏笔审计结果
          "summary": {...}          # 汇总（issue 计数 / 通过/警告项）
        }

    Raises:
        404: 项目或节点不存在。
        400: 节点下无章节计划（无法质检）。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        node_uuid = UUID(req.node_id)
    except ValueError:
        raise HTTPException(400, f"Invalid node_id: {req.node_id}")

    target_node = db.query(OutlineNode).filter(
        OutlineNode.id == node_uuid,
        OutlineNode.project_id == project_id,
    ).first()
    if not target_node:
        raise HTTPException(404, f"OutlineNode {req.node_id} not found")

    # 加载章节计划
    chapter_nodes = (
        db.query(OutlineNode)
        .filter(
            OutlineNode.parent_id == node_uuid,
            OutlineNode.node_type == "chapter_plan",
        )
        .order_by(OutlineNode.sort_order)
        .all()
    )
    if not chapter_nodes:
        raise HTTPException(400, "该节点下无章节计划，请先生成章节大纲再进行质检")

    # 将 OutlineNode 转为质检方法期望的 dict 格式
    def _node_to_check_dict(n: OutlineNode) -> dict:
        """OutlineNode → 质检方法期望的章节 dict。"""
        ex = n.extra or {}
        return {
            "number": n.sort_order + 1,
            "title": n.title or "",
            "core_event": n.summary or "",
            "character_change": n.conflict or "",
            "opening_hook": n.hook or "",
            "end_hook": ex.get("end_hook", n.highlight or ""),
            "foreshadow": ex.get("foreshadow", ""),
            # 因果链四元组（新字段，旧数据可能为空）
            "protagonist_want":     ex.get("protagonist_want", ""),
            "protagonist_obstacle": ex.get("protagonist_obstacle", ""),
            "protagonist_choice":   ex.get("protagonist_choice", ex.get("core_event", "")),
            "choice_cost":          ex.get("choice_cost", ""),
            "villain_action":       ex.get("villain_action", ""),
        }

    chapters = [_node_to_check_dict(n) for n in chapter_nodes]

    # 加载主角信息
    protagonist = db.query(Character).filter(
        Character.project_id == project_id,
        Character.role == "protagonist",
    ).first()
    protagonist_name = protagonist.name if protagonist else "主角"

    # 构建主角心理档案字符串
    protagonist_psychology = ""
    if protagonist:
        parts = []
        if protagonist.fear:
            parts.append(f"核心恐惧/创伤：{protagonist.fear}")
        if protagonist.motivation:
            parts.append(f"当前最强欲望：{protagonist.motivation}")
        if protagonist.values:
            parts.append(f"价值观：{protagonist.values}")
        if protagonist.arc:
            parts.append(f"人物弧线：{protagonist.arc}")
        protagonist_psychology = " | ".join(parts)

    char_summary = ""
    if protagonist:
        char_summary = (
            f"{protagonist.name}（{protagonist.role}，{protagonist.current_realm or '境界未知'}）"
            f"性格：{(protagonist.personality or '')[:80]}"
        )

    story_core = project.story_core if isinstance(project.story_core, dict) else {}
    theme_statement = story_core.get("theme", "")

    # 取上一节点的末章钩子（用于因果链批次衔接检查）
    prior_end_hook = ""
    if chapter_nodes:
        sibling_before = (
            db.query(OutlineNode)
            .filter(
                OutlineNode.parent_id == target_node.parent_id,
                OutlineNode.node_type == "chapter_plan",
                OutlineNode.sort_order < (chapter_nodes[0].sort_order),
            )
            .order_by(OutlineNode.sort_order.desc())
            .first()
        )
        if sibling_before:
            ex = sibling_before.extra or {}
            prior_end_hook = ex.get("end_hook", sibling_before.highlight or "")

    llm_provider_uuid = None
    if req.llm_provider_id:
        try:
            llm_provider_uuid = UUID(req.llm_provider_id)
        except ValueError:
            pass

    svc = AIService(
        profile=req.model_profile,
        db=db,
        llm_provider_id=llm_provider_uuid,
    )

    # 三个专项质检并行执行
    causality_result, arc_result, foreshadow_result = await asyncio.gather(
        svc.outline_check_causality(
            project_title=project.title,
            chapters=chapters,
            prior_end_hook=prior_end_hook,
        ),
        svc.outline_check_character_arc(
            project_title=project.title,
            protagonist_name=protagonist_name,
            chapters=chapters,
            character_summary=char_summary,
            protagonist_psychology=protagonist_psychology,
        ),
        svc.outline_check_foreshadow_audit(
            project_title=project.title,
            theme_statement=theme_statement,
            chapters=chapters,
        ),
    )

    # 聚合统计
    all_issues = (
        causality_result.get("issues", [])
        + arc_result.get("issues", [])
        + foreshadow_result.get("issues", [])
    )

    def _count_severity(issues: list[dict], level: str) -> int:
        return sum(1 for i in issues if i.get("severity") == level)

    checks_passed = []
    checks_warned = []
    for name, result in [
        ("causality", causality_result),
        ("character_arc", arc_result),
        ("foreshadow", foreshadow_result),
    ]:
        if result.get("error"):
            checks_warned.append(name)
        elif result.get("issues"):
            checks_warned.append(name)
        else:
            checks_passed.append(name)

    summary = {
        "total_issues": len(all_issues),
        "critical_count": _count_severity(all_issues, "critical"),
        "high_count": _count_severity(all_issues, "high"),
        "medium_count": _count_severity(all_issues, "medium"),
        "low_count": _count_severity(all_issues, "low"),
        "checks_passed": checks_passed,
        "checks_warned": checks_warned,
        "node_title": target_node.title,
        "chapter_count": len(chapter_nodes),
    }

    return {
        "causality": causality_result,
        "character_arc": arc_result,
        "foreshadow": foreshadow_result,
        "summary": summary,
    }
