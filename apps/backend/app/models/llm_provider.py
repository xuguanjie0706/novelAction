"""可持久化的远程大模型配置（OpenAI 兼容网关）。"""
import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class LlmProvider(Base):
    """创作端选择「Gemini/远程」时使用的默认提供者（见 is_default + enabled）。"""

    __tablename__ = "llm_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键；cover_image_call_logs 等 FK 引用
    name = Column(String(200), nullable=False)  # 展示名（创作端列表）
    base_url = Column(String(2000), nullable=False)  # OpenAI 兼容网关 base URL
    api_key = Column(Text, nullable=True)  # API Key（可空表示环境变量或未配置）
    model_name = Column(String(200), nullable=False)  # 默认模型 id

    provider_type = Column(String(20), default="text", nullable=False, server_default="text")  # text=补全；image=生图网关

    enabled = Column(Boolean, default=True, nullable=False)  # 是否在前端可选
    is_default = Column(Boolean, default=False, nullable=False)  # 是否默认远程提供者
    sort_order = Column(Integer, default=0, nullable=False)  # 列表排序

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）
