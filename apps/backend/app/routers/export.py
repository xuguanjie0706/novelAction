"""
export.py — 导出 & 投稿包路由。

资源边界：仅负责导出相关端点，不涉及质检/AI 建议/记忆等其他业务。

端点列表：
  GET  /projects/{pid}/export/preview          合规预检（字数统计，毫秒响应）
  POST /projects/{pid}/export/scan-violations  AI 违禁词预审（按章节分批扫描）
  GET  /projects/{pid}/export/txt              下载 TXT 全文
  GET  /projects/{pid}/export/outline          下载 TXT 大纲
  GET  /projects/{pid}/export/package          下载 ZIP 投稿包
"""
from __future__ import annotations

import urllib.parse
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chapter, OutlineNode, Project
from app.services.ai_service import AIService
from app.services.export_service import (
    PLATFORM_RULES,
    build_outline_txt,
    build_txt,
    build_zip_package,
    check_compliance,
)

router = APIRouter()

# ── 内部辅助 ──────────────────────────────────────────────────────────────────

def _get_project_or_404(db: Session, project_id: str) -> Project:
    """获取项目，不存在时抛 404。"""
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _get_chapters_for_export(
    db: Session,
    project_id: str,
    include_empty: bool = False,
) -> list[Chapter]:
    """
    按 sort_order 排序获取项目章节。

    Args:
        include_empty: 是否包含无正文章节（默认不含，供合规预检用时为 True）。

    Returns:
        排序后的 Chapter 列表。
    """
    q = db.query(Chapter).filter(Chapter.project_id == project_id)
    if not include_empty:
        q = q.filter(Chapter.word_count > 0)
    return q.order_by(Chapter.sort_order.asc()).all()


def _safe_filename(name: str) -> str:
    """将书名转换为 RFC 5987 编码的 Content-Disposition filename。"""
    encoded = urllib.parse.quote(name, safe="")
    return f"filename*=UTF-8''{encoded}"


# ── 请求/响应模型 ─────────────────────────────────────────────────────────────

class ViolationScanRequest(BaseModel):
    chapter_ids: list[str]                    # 待扫描章节 ID 列表（建议一次 ≤5 章）
    platform: Literal["qidian", "jjwxc", "fanqie", "general"] = "general"
    model_profile: Literal["local", "gemini"] = "local"
    llm_provider_id: Optional[UUID] = None


class ChapterIssueOut(BaseModel):
    chapter_id: str
    title: str
    sort_order: int
    word_count: int
    status: str
    message: str


class ExportPreviewOut(BaseModel):
    total_chapters: int
    total_words: int
    platform: str
    platform_name: str
    compliant_chapters: int
    issues: list[ChapterIssueOut]
    platforms: dict                           # 全部平台规则，供前端选择器使用


class ViolationIssueOut(BaseModel):
    category: str
    level: str
    excerpt: str
    reason: str
    suggestion: str


class ChapterScanResult(BaseModel):
    chapter_id: str
    chapter_title: str
    overall_risk: str
    summary: str
    issues: list[ViolationIssueOut]


class ViolationScanOut(BaseModel):
    results: list[ChapterScanResult]
    total_issues: int
    has_high_risk: bool


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/export/preview", response_model=ExportPreviewOut)
def export_preview(
    project_id: str,
    platform: str = Query("general", description="平台 key：qidian / jjwxc / fanqie / general"),
    db: Session = Depends(get_db),
):
    """
    导出合规预检（纯 DB 查询，毫秒响应，无 AI 调用）。

    返回字数统计、合规章节数，以及不符合平台规则的章节明细。
    同时附带全部平台规则供前端选择器渲染。
    """
    _get_project_or_404(db, project_id)
    chapters = _get_chapters_for_export(db, project_id, include_empty=True)

    if platform not in PLATFORM_RULES:
        platform = "general"

    preview = check_compliance(chapters, platform)

    return ExportPreviewOut(
        total_chapters=preview.total_chapters,
        total_words=preview.total_words,
        platform=preview.platform,
        platform_name=preview.platform_name,
        compliant_chapters=preview.compliant_chapters,
        issues=[ChapterIssueOut(**vars(i)) for i in preview.issues],
        platforms={k: {"name": v["name"], "min_words": v["min_words"], "max_words": v["max_words"]}
                   for k, v in PLATFORM_RULES.items()},
    )


@router.post("/projects/{project_id}/export/scan-violations", response_model=ViolationScanOut)
async def scan_violations(
    project_id: str,
    req: ViolationScanRequest,
    db: Session = Depends(get_db),
):
    """
    AI 违禁词预审：对指定章节列表逐章扫描。

    建议前端每次传入 ≤5 章，避免单次请求超时。
    扫描结果仅供参考，最终判断由作者决定。

    Args:
        req.chapter_ids: 待扫描章节 ID 列表。
        req.platform: 目标平台（影响 AI 判断标准）。
    """
    _get_project_or_404(db, project_id)
    platform_info = PLATFORM_RULES.get(req.platform, PLATFORM_RULES["general"])

    # 按传入顺序查询章节（限制数量防滥用）
    chapter_ids = req.chapter_ids[:10]
    chapters = (
        db.query(Chapter)
        .filter(
            Chapter.project_id == project_id,
            Chapter.id.in_(chapter_ids),
        )
        .all()
    )
    ch_map = {str(c.id): c for c in chapters}

    svc = AIService(
        "gemini" if req.model_profile == "gemini" else "default",
        db=db,
        llm_provider_id=req.llm_provider_id,
    )

    results: list[ChapterScanResult] = []
    for cid in chapter_ids:
        ch = ch_map.get(cid)
        if not ch:
            continue

        # 取纯文本（路由层不引入 chapter_to_plain，避免循环；直接用 re 粗剥 HTML）
        import re
        plain = re.sub(r"<[^>]+>", "", ch.content or "").strip()

        scan = await svc.scan_violations(
            content=plain,
            platform=req.platform,
            platform_name=platform_info["name"],
        )
        results.append(ChapterScanResult(
            chapter_id=cid,
            chapter_title=ch.title or "",
            overall_risk=scan.get("overall_risk", "unknown"),
            summary=scan.get("summary", ""),
            issues=[ViolationIssueOut(**i) for i in scan.get("issues", [])
                    if all(k in i for k in ("category", "level", "excerpt", "reason", "suggestion"))],
        ))

    total_issues = sum(len(r.issues) for r in results)
    has_high_risk = any(r.overall_risk == "high" for r in results)

    return ViolationScanOut(
        results=results,
        total_issues=total_issues,
        has_high_risk=has_high_risk,
    )


@router.get("/projects/{project_id}/export/txt")
def export_txt(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    下载全书 TXT 纯文本。

    自动跳过无正文章节，按 sort_order 排序，章节间双空行分隔。
    Content-Disposition 使用 RFC 5987 编码书名，兼容中文文件名。
    """
    project = _get_project_or_404(db, project_id)
    chapters = _get_chapters_for_export(db, project_id)

    if not chapters:
        raise HTTPException(400, "暂无已完成章节，无法导出")

    txt = build_txt(project, chapters)
    safe_name = _safe_filename(f"{project.title or 'novel'}.txt")

    return Response(
        content=txt.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; {safe_name}",
        },
    )


@router.get("/projects/{project_id}/export/outline")
def export_outline(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    下载全书大纲 TXT（Markdown 风格，卷 → 篇章 → 章节计划树形）。

    输出项目全部 OutlineNode，按层级与 sort_order 组织，
    含各节点摘要/钩子/燃点/冲突/实力里程碑等字段。
    Content-Disposition 使用 RFC 5987 编码书名，兼容中文文件名。
    """
    project = _get_project_or_404(db, project_id)
    nodes = (
        db.query(OutlineNode)
        .filter(OutlineNode.project_id == project_id)
        .order_by(OutlineNode.sort_order.asc())
        .all()
    )

    if not nodes:
        raise HTTPException(400, "暂无大纲内容，无法导出")

    txt = build_outline_txt(project, nodes)
    safe_name = _safe_filename(f"{project.title or 'novel'}_大纲.txt")

    return Response(
        content=txt.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; {safe_name}",
        },
    )


@router.get("/projects/{project_id}/export/package")
def export_package(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    下载 ZIP 投稿包（全文 + 分章文件 + 清单）。

    ZIP 结构：{书名}/manifest.txt + full_manuscript.txt + chapters/{序号_标题}.txt。
    适合同时投稿多个平台时按需选取单章文件。
    """
    project = _get_project_or_404(db, project_id)
    chapters = _get_chapters_for_export(db, project_id)

    if not chapters:
        raise HTTPException(400, "暂无已完成章节，无法打包")

    zip_bytes = build_zip_package(project, chapters)
    safe_name = _safe_filename(f"{project.title or 'novel'}_投稿包.zip")

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; {safe_name}",
        },
    )
