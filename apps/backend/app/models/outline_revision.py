from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class OutlineRevision(Base):
    """Immutable outline snapshot for QA/repair history."""
    __tablename__ = "outline_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id

    label = Column(String(200), nullable=False)  # 快照标签（人读）
    source = Column(String(40), default="manual")  # 来源：manual / pre_repair / post_repair / quality
    scope = Column(String(20), default="book")  # 快照范围：book 全书 / volume 单卷
    volume_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)  # FK → outline_nodes.id；scope=volume 时指向卷节点
    note = Column(Text)  # 备注
    snapshot = Column(JSON, nullable=False)  # 大纲树不可变快照（节点全量）
    meta = Column(JSON, default=dict)  # 附加元数据
    node_count = Column(Integer, default=0)  # 快照内节点数（便于展示）

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 快照时间（UTC）
