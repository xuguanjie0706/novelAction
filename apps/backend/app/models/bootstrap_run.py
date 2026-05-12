"""
BootstrapRun — LangGraph Bootstrap 运行记录表。

职责：
  - 跨请求持久化每次 bootstrap 的生命周期（pending → running → awaiting_gate → done / failed）
  - 保存 SSE 事件日志（events 字段），供重连时 replay
  - 保存 gate_data（Step 0 立项定位结果），前端在闸门处展示并可编辑后提交 resume

表与 LangGraph MemorySaver 的关系：
  - LangGraph 的 thread_id = run.id（UUID）
  - 本表负责业务状态 + 事件日志；MemorySaver 负责图执行的 checkpoint（内存）
  - 未来若换 PostgresSaver（需 psycopg3），本表仍保留，作为业务层的 source of truth
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class BootstrapRun(Base):
    """每次调用 POST /bootstrap/runs 生成一行。run.id 同时作为 LangGraph thread_id。"""

    __tablename__ = "bootstrap_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="run_id，同时是 LangGraph thread_id；前端全程用此 id 订阅 SSE / 提交 resume",
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="发起用户；NULL 仅出现在无鉴权兼容模式",
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Step 1 project 节点落库后回填；初始 NULL",
    )

    # ── 生命周期 ─────────────────────────────────────────────────────────
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        comment=(
            "pending     — 已创建，尚未开始\n"
            "running     — 图正在执行\n"
            "awaiting_gate — 在立项定位闸门暂停，等待用户确认/修改\n"
            "done        — 全部步骤完成\n"
            "failed      — 不可恢复错误"
        ),
    )
    error_message = Column(Text, nullable=True, comment="failed 时的错误摘要")

    # ── 输入参数（只写一次，供 replay / debug 查阅）────────────────────
    logline = Column(Text, nullable=False)
    mode = Column(String(20), nullable=False, default="sequential", comment="sequential | single_shot")
    model_profile = Column(String(20), nullable=False, default="gemini")

    # ── 闸门数据（Step 0 → gate 节点产出，等待用户确认）───────────────
    gate_data = Column(
        JSON,
        nullable=True,
        comment="positioning 结果 JSON；awaiting_gate 时前端读取并展示，resume 时用户可覆写",
    )

    # ── SSE 事件日志（追加写，支持重连 replay）─────────────────────────
    events = Column(
        JSON,
        nullable=False,
        default=list,
        comment="所有 SSE 事件的 JSON 数组；新订阅者先 replay 已有事件再订阅实时队列",
    )

    # ── 时间戳 ───────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
