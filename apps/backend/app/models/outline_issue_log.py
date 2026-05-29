"""大纲问题台账（OutlineIssueLog）。

动机：把每次大纲质检（linter + LLM QA）产出的问题逐条落库，
形成可统计的「高频问题」基线，供生成期回灌（reduce at source）与修复收敛使用。
持久化优先硬规则要求：问题信号不能只停在卷节点 extra 里，需可跨卷/跨次聚合查询。
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class OutlineIssueLog(Base):
    """单条大纲质检问题记录（按 project + 卷 + 指纹去重）。"""

    __tablename__ = "outline_issue_logs"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "volume_node_id", "fingerprint",
            name="uq_outline_issue_project_volume_fingerprint",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    volume_node_id = Column(UUID(as_uuid=True), ForeignKey("outline_nodes.id"), nullable=True)

    rule_id = Column(String(40), nullable=False)        # 规则/维度标识，如 CH-04、SEQ-07
    dimension = Column(String(40), nullable=False)       # 归一化维度，见 contract.dimension_for_rule
    severity = Column(String(20), nullable=False, default="medium")  # critical/high/medium/low
    source = Column(String(20), nullable=False, default="linter")    # linter/qa_cheap/qa_holistic
    field = Column(String(80))                           # 命中字段，如 extra.choice_cost
    chapter_number = Column(Integer)                     # 卷内章号（无则空）
    message = Column(Text, nullable=False)               # 问题描述
    suggestion = Column(Text)                            # 修复建议
    fingerprint = Column(String(64), nullable=False)     # 与 project+volume 组成唯一键
    occurrence_count = Column(Integer, nullable=False, default=1)  # 同指纹累计命中次数

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    project = relationship("Project")
