"""
draft_graph — 章节起草 LangGraph 包。

对外接口（供 routers/jobs.py 调用）：
  run_draft_job(job_id, ...)   — 从头启动图（background task）
  resume_draft_job(job_id, user_input)  — resume 被 interrupt 的图（background task）
  subscribe(job_id)            — 订阅实时 SSE Queue
  unsubscribe(job_id, q)       — 注销 SSE Queue

不对外暴露 nodes / state / graph 内部实现细节，仅通过上述函数交互。
"""
from app.services.draft_graph.graph import run_draft_job, resume_draft_job, subscribe, unsubscribe

__all__ = ["run_draft_job", "resume_draft_job", "subscribe", "unsubscribe"]
