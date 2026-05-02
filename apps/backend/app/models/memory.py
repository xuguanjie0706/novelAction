from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base
from app.config import settings

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class MemoryChunk(Base):
    """
    长篇记忆库 — 每章写完后自动提取关键记忆条目
    embedding 字段用于语义检索，AI 质检时按相关度召回
    """
    __tablename__ = "memory_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)

    # 记忆类型
    memory_type = Column(String(30), default="event")
    # event=事件, character_state=人物状态, foreshadow=伏笔, setting=设定确认, conflict=冲突

    title = Column(String(200))
    content = Column(Text, nullable=False)         # 记忆正文
    chapter_number = Column(Integer)               # 发生在第几章
    tags = Column(JSON, default=list)              # ["林默", "青云宗", "关键伏笔"]

    # pgvector embedding — 维度由 EMBEDDING_DIM 配置项决定（nomic-embed-text = 768）
    # 如果 pgvector 未安装则跳过
    if HAS_PGVECTOR:
        embedding = Column(Vector(settings.EMBEDDING_DIM))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="memory_chunks")
