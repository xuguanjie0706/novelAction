from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class OutlineRevision(Base):
    """Immutable outline snapshot for QA/repair history."""
    __tablename__ = "outline_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    label = Column(String(200), nullable=False)
    source = Column(String(40), default="manual")  # manual / pre_repair / post_repair / quality
    scope = Column(String(20), default="book")     # book / volume
    volume_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)
    note = Column(Text)
    snapshot = Column(JSON, nullable=False)
    meta = Column(JSON, default=dict)
    node_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
