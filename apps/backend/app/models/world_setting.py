from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class SettingCategory(Base):
    """设定分类: 修炼体系 / 势力 / 地理 / 规则 / 道具 ..."""
    __tablename__ = "setting_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)   # e.g. "修炼体系"
    icon = Column(String(50))                    # emoji or icon name
    sort_order = Column(Integer, default=0)

    settings = relationship("WorldSetting", back_populates="category")


class WorldSetting(Base):
    """单张设定卡"""
    __tablename__ = "world_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("setting_categories.id"), nullable=True)

    title = Column(String(200), nullable=False)
    content = Column(Text)                        # 富文本内容
    tags = Column(JSON, default=list)             # ["境界", "突破条件"]
    extra = Column(JSON, default=dict)            # 扩展字段，如境界列表

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="world_settings")
    category = relationship("SettingCategory", back_populates="settings")
