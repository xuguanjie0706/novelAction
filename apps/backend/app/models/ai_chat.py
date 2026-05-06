from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class AiChatMessage(Base):
    """AI 助手对话消息，按项目 + 上下文持久化。"""
    __tablename__ = "ai_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id；章内助手时有值

    context_type = Column(String(20), default="general", nullable=False)  # 会话上下文：general / chapter 等
    role = Column(String(20), nullable=False)  # user / assistant / system（与 OpenAI 消息 role 对齐）
    content = Column(Text, nullable=False)  # 消息正文

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 发送时间（UTC）

    project = relationship("Project", back_populates="ai_chat_messages")
    chapter = relationship("Chapter", back_populates="ai_chat_messages")
