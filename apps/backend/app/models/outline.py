from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class OutlineNode(Base):
    """
    大纲树节点，支持任意层级:
      volume (卷) → arc (篇章) → chapter_plan (章节计划)
    parent_id=None 表示根节点（卷级别）
    """
    __tablename__ = "outline_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)

    node_type = Column(String(20), default="arc")  # volume / arc / chapter_plan
    title = Column(String(300), nullable=False)
    summary = Column(Text)                          # 情节摘要
    hook = Column(Text)                             # 钩子/悬念
    highlight = Column(Text)                        # 燃点
    conflict = Column(Text)                         # 冲突
    sort_order = Column(Integer, default=0)
    extra = Column(JSON, default=dict)

    # 追读分析（针对 chapter_plan）
    reader_hook_score = Column(Integer)             # 1-10 钩子强度预估
    expected_words = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="outline_nodes")
    parent = relationship("OutlineNode", remote_side=[id], back_populates="children")
    children = relationship("OutlineNode", back_populates="parent", cascade="all, delete-orphan")
    chapter = relationship("Chapter", back_populates="outline_node", uselist=False)
