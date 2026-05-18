"""
GenerationJob — 章节起草等 AI 生成任务的持久化队列记录。

设计动机：
  旧的 gated_draft_routes.py 以 StreamingResponse 绑定 HTTP 请求生命周期，
  前端断线即中断生成。本表将「任务」与「连接」彻底解耦：

  - 后台 asyncio 任务负责执行 LangGraph 图，生命周期绑定进程而非请求。
  - SSE/WebSocket 只是「观察者」，断线重连后从 events 字段 replay 所有历史事件。
  - human interrupt 通过 status=waiting_input + user_input 字段实现跨请求通信。

状态机：
  pending → running → [waiting_input ⇌ running ...] → completed | failed | cancelled
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class GenerationJob(Base):
    """每次 POST /jobs 创建一行；job.id 同时作为 LangGraph thread_id。"""

    __tablename__ = "generation_jobs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="job_id，同时是 LangGraph thread_id；前端全程用此 id 订阅 WS / 提交 input",
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── 任务类型与生命周期 ───────────────────────────────────────────────
    job_type = Column(
        String(30),
        nullable=False,
        default="chapter_draft",
        comment="chapter_draft | scene_plan | outline_expand",
    )
    status = Column(
        String(30),
        nullable=False,
        default="pending",
        comment=(
            "pending       — 已入队，等待 worker 拾取\n"
            "running       — 图正在执行\n"
            "waiting_input — 在 human interrupt 节点暂停，等待用户决策\n"
            "completed     — 所有节点执行完毕，结果已落库\n"
            "failed        — 不可恢复错误\n"
            "cancelled     — 用户主动取消"
        ),
    )
    current_node = Column(
        String(60),
        nullable=True,
        comment="当前正在执行的图节点名称，供前端进度展示",
    )
    progress_pct = Column(
        Integer,
        nullable=False,
        default=0,
        comment="0-100 进度百分比，由各节点手动推进",
    )

    # ── 任务输入（只写一次，供 replay / debug）──────────────────────────
    input_payload = Column(
        JSON,
        nullable=False,
        default=dict,
        comment=(
            "提交时的全部参数：\n"
            "chapter_id, outline_node_id, model_profile, llm_provider_id,\n"
            "user_directives, quality_threshold, skip_blueprint_review,\n"
            "skip_quality_review, max_iterations"
        ),
    )

    # ── human interrupt 通信 ────────────────────────────────────────────
    user_input_schema = Column(
        JSON,
        nullable=True,
        comment=(
            "waiting_input 时告知前端需要什么输入（JSON Schema），例如：\n"
            '{"type": "blueprint_review", "scene_blueprint": [...], '
            '"options": ["approve","rewrite","skip"]}'
        ),
    )
    user_input = Column(
        JSON,
        nullable=True,
        comment=(
            "前端通过 POST /jobs/{id}/input 提交的决策；\n"
            'graph resume 时作为 Command(resume=...) 注入，例如：\n'
            '{"action": "rewrite", "directive": "第二场改成夜袭"}'
        ),
    )

    # ── SSE 事件日志（追加写，支持重连 replay）─────────────────────────
    events = Column(
        JSON,
        nullable=False,
        default=list,
        comment="所有 SSE 事件的 JSON 数组；新订阅者先 replay 已有事件再订阅实时队列",
    )

    # ── 任务结果 ────────────────────────────────────────────────────────
    result = Column(
        JSON,
        nullable=True,
        comment="completed 时的产物引用：{chapter_id, word_count, quality_score, scene_ids}",
    )
    error_detail = Column(Text, nullable=True, comment="failed 时的错误详情")

    # ── 时间戳 ──────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="completed / failed / cancelled 时写入",
    )
