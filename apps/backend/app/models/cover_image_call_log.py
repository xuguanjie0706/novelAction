"""AI 封面图片网关调用记录（便于对照网关计费与本地解析失败原因）。"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class CoverImageCallLog(Base):
    __tablename__ = "cover_image_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    llm_provider_id = Column(UUID(as_uuid=True), ForeignKey("llm_providers.id"), nullable=False, index=True)

    provider_name = Column(String(200), nullable=False, default="")
    model_name = Column(String(200), nullable=False, default="")
    prompt = Column(Text, nullable=False, default="")
    size = Column(String(32), nullable=False, default="")
    quality = Column(String(20), nullable=False, default="")
    store_compressed = Column(Boolean, nullable=False, default=True)

    # ok | upstream_network | upstream_http | upstream_empty | upstream_bad_json | decode_error | compress_error
    status = Column(String(40), nullable=False)
    http_status = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)

    # b64_json | url
    response_kind = Column(String(20), nullable=False, default="")
    # 不含 api_key，仅用于对照配置（如 https://host/v1/images/generations）
    gateway_url = Column(String(2000), nullable=False, default="")

    # 相对后端工作目录的调试目录，如 data/covers/debug/<stem>/（内含 meta.json、payload.b64.txt 等）
    debug_bundle_rel_path = Column(String(1000), nullable=True)

    # 成功时站内 cover_url（/api/v1/covers/files/…）或外链 image_url；供管理后台预览
    result_cover_url = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
