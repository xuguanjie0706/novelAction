from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Float, Integer, JSON
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)  # FK → chapters.id；提取该章时的出处（可空）

    # 记忆类型
    memory_type = Column(String(30), default="event")  # event / character_state / foreshadow / setting / conflict

    title = Column(String(200))  # 记忆条目标题（检索展示）
    content = Column(Text, nullable=False)         # 记忆正文
    chapter_number = Column(Integer)               # 发生在第几章
    tags = Column(JSON, default=list)              # ["林默", "青云宗", "关键伏笔"]

    # 重要度与访问统计（时效衰减检索 + 热度重排序依据）
    importance_score = Column(Float, default=0.5)      # AI 提取时赋值 0.0-1.0；越高越优先召回
    access_count = Column(Integer, default=0)          # 被 RAG 召回的累计次数
    last_accessed_at = Column(DateTime(timezone=True)) # 最近一次被召回时间（UTC）

    # pgvector embedding — 维度由 EMBEDDING_DIM 配置项决定（默认 BAAI/bge-m3 = 1024）
    # 如果 pgvector 未安装则跳过；换模型/维度后需运行 migration b3c4d5e6f7a8 并补跑 verify_pgvector.py --reembed
    if HAS_PGVECTOR:
        embedding = Column(Vector(settings.EMBEDDING_DIM))  # pgvector 向量；维度见 EMBEDDING_DIM

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 写入时间（UTC）

    project = relationship("Project", back_populates="memory_chunks")
