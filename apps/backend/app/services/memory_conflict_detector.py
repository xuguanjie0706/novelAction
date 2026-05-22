"""
记忆冲突自动检测服务

职责：
  扫描项目全量 MemoryChunk，通过 AI 识别四类冲突：
  - character_state  : 角色状态前后矛盾（死亡后仍活动、境界倒退等）
  - timeline         : 时间线逻辑矛盾（同一事件记录不一致、发生顺序倒置）
  - attribute        : 实体属性描述冲突（道具描述不一致、地点信息矛盾）
  - foreshadow       : 伏笔管理冲突（伏笔在埋设前即被回收）

检测流程：
  1. 从 DB 拉取全量 MemoryChunk，按 memory_type 分组
  2. 构建紧凑摘要列表（id短码 + 章节号 + title + content片段）
  3. 调用 AI 返回冲突 JSON 数组
  4. 解析结果，将短码映射回真实 UUID
  5. 写入 Project.extra.memory_conflicts（持久化）并返回报告
  6. 写入 memory_conflict_detect_logs（每次运行一条，供管理端观测）

限制：
  - 单次扫描最多 200 条 chunk（超出时按 importance_score 降序截取）
  - AI 输出超过 50 条冲突时只保留 severity=high/medium 的条目
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.memory import MemoryChunk
from app.models.project import Project
from app.services.memory_conflict_detect_log import persist_memory_conflict_detect_log

logger = logging.getLogger(__name__)

_MAX_CHUNKS = 200          # 单次扫描上限
_MAX_CONFLICTS_KEEP = 50   # 保存上限，超出时剪裁低严重度条目
_CONTENT_PREVIEW = 80      # 摘要截取长度（字符）


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _short_id(uid) -> str:
    """取 UUID 前8位作短码，用于 prompt 中减少 token 用量。"""
    return str(uid)[:8]


def _build_chunk_summary_block(chunks: List[MemoryChunk]) -> str:
    """
    将记忆条目列表格式化为 AI prompt 用的紧凑摘要块。

    格式（每行一条）：
      [短码] 第N章 <type> ▸ title — content片段
    """
    lines = []
    for c in chunks:
        ch = f"第{c.chapter_number}章" if c.chapter_number else "设定"
        content_preview = (c.content or "")[:_CONTENT_PREVIEW].replace("\n", " ")
        lines.append(
            f"[{_short_id(c.id)}] {ch} <{c.memory_type}> ▸ {c.title or '无标题'} — {content_preview}"
        )
    return "\n".join(lines)


def _parse_conflict_json(text: str) -> List[Dict[str, Any]]:
    """
    从 AI 输出中解析冲突 JSON 数组，容忍 markdown fence 包裹。

    Returns:
        冲突字典列表；解析失败时返回空列表。
    """
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("["):
                t = part
                break
    try:
        data = json.loads(t)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _build_id_map(chunks: List[MemoryChunk]) -> Dict[str, UUID]:
    """构建「短码 → 真实 UUID」映射。"""
    return {_short_id(c.id): c.id for c in chunks}


def _resolve_chunk_ids(short_ids: List[str], id_map: Dict[str, UUID]) -> List[UUID]:
    """将 AI 返回的短码列表映射回真实 UUID，忽略无法识别的条目。"""
    result = []
    for sid in short_ids or []:
        real_id = id_map.get(str(sid)[:8])
        if real_id:
            result.append(real_id)
    return result


def _trim_conflicts(conflicts: List[Dict]) -> List[Dict]:
    """超出上限时，优先保留 high / medium 严重度条目。"""
    if len(conflicts) <= _MAX_CONFLICTS_KEEP:
        return conflicts
    high = [c for c in conflicts if c.get("severity") == "high"]
    medium = [c for c in conflicts if c.get("severity") == "medium"]
    low = [c for c in conflicts if c.get("severity") == "low"]
    trimmed = (high + medium + low)[:_MAX_CONFLICTS_KEEP]
    logger.info(
        "Conflict trim: %d → %d (high=%d medium=%d low=%d)",
        len(conflicts), len(trimmed), len(high), len(medium), len(low),
    )
    return trimmed


# ---------------------------------------------------------------------------
# 主函数（供路由层调用）
# ---------------------------------------------------------------------------

async def detect_memory_conflicts(
    db: Session,
    project_id: str | UUID,
    ai_service,
    *,
    max_chunks: int = _MAX_CHUNKS,
    trigger: str = "manual",
    chapter_id: str | UUID | None = None,
) -> Dict[str, Any]:
    """
    扫描项目记忆库并用 AI 检测冲突，结果持久化写入 Project.extra.memory_conflicts。

    Args:
        db:          数据库 session
        project_id:  目标项目 ID
        ai_service:  已初始化的 AIService 实例（用于调用 LLM）
        max_chunks:  单次扫描上限（默认 200）
        trigger:     触发来源（manual | chapter_debrief）
        chapter_id:  复盘触发的章节 ID（可选）

    Returns:
        冲突报告字典（含 project_id / total_chunks_scanned / conflicts / detected_at）
    """
    pid = str(project_id)
    started = time.perf_counter()

    def _finish(
        report: Dict[str, Any],
        *,
        status: str,
        error: str | None = None,
    ) -> Dict[str, Any]:
        persist_memory_conflict_detect_log(
            db,
            project_id=pid,
            chapter_id=chapter_id,
            trigger=trigger,
            status=status,
            duration_ms=int((time.perf_counter() - started) * 1000),
            total_chunks_scanned=int(report.get("total_chunks_scanned") or 0),
            conflict_count=len(report.get("conflicts") or []),
            error=error or (str(report["error"]) if report.get("error") else None),
            report=report,
        )
        return report

    # 1. 拉取全量 chunk，按重要度降序截取
    chunks: List[MemoryChunk] = (
        db.query(MemoryChunk)
        .filter(MemoryChunk.project_id == pid)
        .order_by(
            MemoryChunk.importance_score.desc().nullslast(),
            MemoryChunk.chapter_number.asc().nullslast(),
        )
        .limit(max_chunks)
        .all()
    )

    if not chunks:
        logger.info("detect_memory_conflicts: project %s has no memory chunks", pid)
        report = {
            "project_id": pid,
            "total_chunks_scanned": 0,
            "conflicts": [],
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }
        _persist_report(db, project_id, report)
        return _finish(report, status="skipped")

    id_map = _build_id_map(chunks)
    summary_block = _build_chunk_summary_block(chunks)

    # 2. 构建 prompt
    system_prompt = (
        "你是小说记忆一致性审查员。你的任务是从记忆库摘要中识别前后矛盾的条目，"
        "严格返回 JSON 数组，不输出任何其他内容。"
    )
    user_prompt = f"""以下是该小说项目的记忆库摘要（共 {len(chunks)} 条）。
每条格式：[短码] 章节 <类型> ▸ 标题 — 内容片段

{summary_block}

请识别以下四类冲突并返回 JSON 数组：
1. character_state：角色状态前后矛盾（死亡后仍活动、境界倒退、位置冲突等）
2. timeline：时间线逻辑矛盾（同一事件不同版本、发生顺序颠倒）
3. attribute：实体属性描述冲突（道具/地点/势力描述不一致）
4. foreshadow：伏笔管理冲突（伏笔在埋设前即被回收，或回收与埋设章节错误）

仅报告确实存在的冲突，不要捏造。若无冲突则返回空数组 []。

返回格式（JSON 数组，每项结构如下）：
[
  {{
    "conflict_type": "character_state",
    "severity": "high",
    "description": "林默在第5章已战死，但第8章记录他参与青云会议",
    "chunk_ids": ["短码1", "短码2"],
    "chapter_refs": [5, 8]
  }}
]

severity 取值：high（明确矛盾）/ medium（疑似矛盾需人工确认）/ low（轻微不一致）
只返回 JSON，不要解释。"""

    # 3. 调用 AI
    try:
        response = await ai_service._call_ai(
            system_prompt,
            user_prompt,
            max_tokens=2048,
            context={"operation": "memory_conflict_detect", "project_id": pid},
            task="memory.conflict_detect",
        )
    except Exception as exc:
        logger.warning("detect_memory_conflicts AI call failed: %s", exc)
        report = {
            "project_id": pid,
            "total_chunks_scanned": len(chunks),
            "conflicts": [],
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
        }
        _persist_report(db, project_id, report)
        return _finish(report, status="error", error=str(exc))

    # 4. 解析 + 映射短码
    raw_conflicts = _parse_conflict_json(response)
    conflicts_out = []
    for item in _trim_conflicts(raw_conflicts):
        resolved_ids = _resolve_chunk_ids(item.get("chunk_ids", []), id_map)
        conflicts_out.append({
            "conflict_type": item.get("conflict_type", "unknown"),
            "severity": item.get("severity", "low"),
            "description": item.get("description", ""),
            "chunk_ids": [str(cid) for cid in resolved_ids],
            "chapter_refs": [int(r) for r in (item.get("chapter_refs") or []) if str(r).isdigit()],
        })

    report = {
        "project_id": pid,
        "total_chunks_scanned": len(chunks),
        "conflicts": conflicts_out,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }

    _persist_report(db, project_id, report)
    logger.info(
        "detect_memory_conflicts: project=%s scanned=%d conflicts=%d",
        pid, len(chunks), len(conflicts_out),
    )
    return _finish(report, status="ok")


def _persist_report(db: Session, project_id: str | UUID, report: Dict[str, Any]) -> None:
    """将冲突报告写入 Project.extra.memory_conflicts（持久化）。"""
    try:
        project = db.query(Project).filter(Project.id == str(project_id)).first()
        if project is None:
            logger.warning("_persist_report: project %s not found", project_id)
            return
        extra = dict(project.extra or {})
        extra["memory_conflicts"] = report
        project.extra = extra
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("_persist_report failed: %s", exc)
