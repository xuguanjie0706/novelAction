"""可持久化的远程大模型配置（OpenAI 兼容网关）。"""
import uuid
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class LlmProvider(Base):
    """创作端选择「Gemini/远程」时使用的默认提供者（见 is_default + enabled）。"""

    __tablename__ = "llm_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    base_url = Column(String(2000), nullable=False)
    api_key = Column(Text, nullable=True)
    model_name = Column(String(200), nullable=False)

    # text = 文本生成（默认）；image = 图片生成（DALL-E / Flux 等兼容 /v1/images/generations）
    provider_type = Column(String(20), default="text", nullable=False, server_default="text")

    enabled = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
