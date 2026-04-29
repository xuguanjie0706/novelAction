import uuid

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class LlmCallLog(Base):
    __tablename__ = "llm_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mode = Column(String(40), nullable=False, default="default")
    model = Column(String(200), nullable=False, default="")
    llm_endpoint = Column(String(2000), nullable=False, default="")
    status = Column(String(20), nullable=False, default="ok")
    duration_ms = Column(Integer, nullable=False, default=0)
    context = Column(JSON, nullable=False, default=dict)
    token_usage = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    input_payload = Column(JSON, nullable=True)
    output_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
