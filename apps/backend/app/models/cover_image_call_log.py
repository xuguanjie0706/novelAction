"""AI 封面图片网关调用记录（便于对照网关计费与本地解析失败原因）。"""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class CoverImageCallLog(Base):
    __tablename__ = "cover_image_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)  # FK → projects.id，封面所属书
    llm_provider_id = Column(UUID(as_uuid=True), ForeignKey("llm_providers.id"), nullable=False, index=True)  # FK → llm_providers.id

    provider_name = Column(String(200), nullable=False, default="")  # 冗余：网关/厂商展示名
    model_name = Column(String(200), nullable=False, default="")  # 生图模型名
    prompt = Column(Text, nullable=False, default="")  # 完整生图 prompt
    size = Column(String(32), nullable=False, default="")  # 请求尺寸，如 1024x1024
    quality = Column(String(20), nullable=False, default="")  # 质量档位（依网关）
    store_compressed = Column(Boolean, nullable=False, default=True)  # 是否落盘压缩图

    status = Column(String(40), nullable=False)  # ok / upstream_network / upstream_http / upstream_empty / upstream_bad_json / decode_error / compress_error
    http_status = Column(Integer, nullable=True)  # 上游 HTTP 状态码
    error_message = Column(Text, nullable=True)  # 失败时的错误信息
    duration_ms = Column(Integer, nullable=False, default=0)  # 调用耗时毫秒

    response_kind = Column(String(20), nullable=False, default="")  # 响应形态：b64_json / url
    gateway_url = Column(String(2000), nullable=False, default="")  # 实际请求 URL（不含 api_key）

    debug_bundle_rel_path = Column(String(1000), nullable=True)  # 调试包相对路径（meta、b64 落盘等）

    result_cover_url = Column(Text, nullable=True)  # 成功后的站内或外链封面地址

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)  # 调用时间（UTC）
