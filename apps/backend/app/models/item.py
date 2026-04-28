from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class Item(Base):
    """
    道具/法宝/装备 — 世界中存在的重要物品

    item_type 分类:
      weapon      武器（剑/刀/枪/弓）
      armor       防具（甲胄、护符）
      pill        丹药（突破丹、疗伤丹）
      artifact    法宝（储物戒、传送阵盘）
      material    材料（天材地宝、炼器材料）
      scroll      功法书/典籍/卷轴
      beast       神兽/宠物（有灵性的存在）
      other       其他

    rarity 稀有度（由低到高）:
      common      凡品/普通
      uncommon    精品
      rare        稀有
      epic        极品
      legendary   传说
      mythic      神话
      unique      唯一（故事专属）
    """
    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)

    name = Column(String(100), nullable=False)           # 道具名称，如"混沌玉简"
    item_type = Column(String(20), default="artifact")   # weapon/armor/pill/artifact/material/scroll/beast/other
    rarity = Column(String(20), default="rare")          # common/uncommon/rare/epic/legendary/mythic/unique

    description = Column(Text)                           # 道具完整描述与外观
    origin = Column(Text)                                # 来历（上古遗留、某宗门镇宗之宝等）
    effects = Column(Text)                               # 能力与效果
    limitations = Column(Text)                           # 使用限制（境界要求、次数、副作用）

    # 当前持有者（character UUID）
    current_owner_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=True)

    # 持有历史记录：[{owner_name, chapter, event_description}]
    ownership_history = Column(JSON, default=list)

    # 道具在故事中的作用
    story_significance = Column(Text)                   # 在故事中的重要性/象征意义
    first_appearance_chapter = Column(Integer)          # 首次登场章节

    # 道具状态
    status = Column(String(20), default="intact")       # intact=完整 damaged=受损 destroyed=毁灭 lost=遗失 unknown=下落不明

    sort_order = Column(Integer, default=0)
    extra = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project", back_populates="items")
    current_owner = relationship("Character", foreign_keys=[current_owner_id])
