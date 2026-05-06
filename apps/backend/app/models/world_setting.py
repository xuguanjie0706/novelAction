from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class SettingCategory(Base):
    """设定分类: 修炼体系 / 势力 / 地理 / 规则 / 道具 ..."""
    __tablename__ = "setting_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    name = Column(String(100), nullable=False)  # 分类名，如「修炼体系」
    icon = Column(String(50))  # 展示用 emoji 或图标名
    sort_order = Column(Integer, default=0)  # 侧边栏排序

    settings = relationship("WorldSetting", back_populates="category")


class WorldSetting(Base):
    """单张设定卡"""
    __tablename__ = "world_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id
    category_id = Column(UUID(as_uuid=True), ForeignKey("setting_categories.id"), nullable=True)  # FK → setting_categories.id；可空=未分类

    title = Column(String(200), nullable=False)  # 设定卡标题
    content = Column(Text)  # 正文（富文本）
    tags = Column(JSON, default=list)  # 检索标签，如 ["境界","突破条件"]
    extra = Column(JSON, default=dict)  # JSON 扩展（如结构化境界表）

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="world_settings")
    category = relationship("SettingCategory", back_populates="settings")
