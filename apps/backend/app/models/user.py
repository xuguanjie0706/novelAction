"""用户模型（认证系统）。

职责：存储注册用户的账号凭证；与业务实体（Project 等）无直接 FK 关联，
目前采用「单一全局账号池」设计，后续可按需扩展 project_id 归属。

禁止事项：不要在此模块存储 AI 相关配置，那些字段属于 LlmProvider。
"""

from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class User(Base):
    """注册用户。

    Attributes:
        id: UUID 主键。
        email: 登录邮箱，唯一索引，不可为空。
        username: 显示名称，可选。
        hashed_password: bcrypt 哈希后的密码；原文永不落库。
        is_active: 账号是否有效；管理员可停用而不删除记录。
        created_at: 注册时间（UTC，数据库默认填充）。
        updated_at: 最后更新时间（UTC，更新时自动刷新）。
    """

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
