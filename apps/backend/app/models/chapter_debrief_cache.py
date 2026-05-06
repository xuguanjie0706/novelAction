from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChapterDebriefCache(Base):
    __tablename__ = "chapter_debrief_caches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=False, unique=True)  # FK → chapters.id；每章一条 LLM 复盘缓存
    content_hash = Column(String(64), nullable=False, default="")  # 章节正文哈希；变则缓存失效
    model_profile = Column(String(20), nullable=False, default="local")  # 生成缓存时用的模型档
    llm_provider_id = Column(String(36), nullable=True)  # 可选：提供者 UUID 字符串（与 LlmProvider.id 对应）
    payload = Column(JSON, nullable=False, default=dict)  # 复盘 LLM 原始/解析结果缓存体
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 首次写入（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 刷新时间（UTC）
