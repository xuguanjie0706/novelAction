from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class StoryLine(Base):
    """
    故事线 — 小说中并行推进的多条叙事线索

    类型示例:
      main        主线（主角成长/复仇/争霸）
      sub         支线（配角剧情、世界扩展）
      romance     感情线（感情发展、CP 互动）
      growth      成长线（修炼突破节奏）
      mystery     悬疑/伏笔线（逐步揭开谜题）
      faction     势力线（势力博弈、战争）
      antagonist  反派线（反派目标与行动）
    """
    __tablename__ = "story_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # 主键；复盘 undo 里存 storyline_id
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)  # FK → projects.id

    name = Column(String(100), nullable=False)           # 故事线名称，如"主线：逆天改命"
    line_type = Column(String(30), default="main")       # main/sub/romance/growth/mystery/faction/antagonist
    description = Column(Text)                           # 故事线简述与核心矛盾

    # 状态与进度
    status = Column(String(20), default="planned")       # planned/active/climax/resolved/dropped
    start_chapter = Column(Integer)                      # 在第几章启动
    end_chapter = Column(Integer)                        # 预计在第几章结束

    # 关联人物（存 character_id UUID 列表）
    related_character_ids = Column(JSON, default=list)  # 关联人物 UUID 列表（→ characters.id）

    # 关键节拍 — 每个元素：{chapter_range, beat, milestone}
    key_beats = Column(JSON, default=list)  # 结构化节拍与里程碑

    # 故事线的核心冲突与解决方向
    core_conflict = Column(Text)                         # 核心矛盾是什么
    resolution_direction = Column(Text)                  # 预计如何解决

    sort_order = Column(Integer, default=0)  # 列表排序
    extra = Column(JSON, default=dict)  # JSON 扩展字段

    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 创建时间（UTC）
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())  # 更新时间（UTC）

    project = relationship("Project", back_populates="story_lines")
