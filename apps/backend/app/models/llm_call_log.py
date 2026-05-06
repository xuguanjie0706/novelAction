import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class LlmCallLog(Base):
    __tablename__ = "llm_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    mode = Column(String(40), nullable=False, default="default")  # 调用场景/任务模式标识
    model = Column(String(200), nullable=False, default="")  # 实际请求的模型名
    llm_endpoint = Column(String(2000), nullable=False, default="")  # 请求 URL（脱敏）
    status = Column(String(20), nullable=False, default="ok")  # ok / error 等
    duration_ms = Column(Integer, nullable=False, default=0)  # 耗时毫秒
    context = Column(JSON, nullable=False, default=dict)  # 业务上下文（project_id、task 等，依调用方写入）
    token_usage = Column(JSON, nullable=False, default=dict)  # token 统计 {prompt, completion, ...}
    error = Column(Text, nullable=True)  # 失败时的错误文本
    input_payload = Column(JSON, nullable=True)  # 请求体摘要或全量（注意体积与隐私）
    output_payload = Column(JSON, nullable=True)  # 响应摘要或全量
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # 调用时间（UTC）
