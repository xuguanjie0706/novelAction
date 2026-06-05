"""质检根因台账（QualityRootCauseLog）。

动机
----
现有质检（``quality_check``）只把最新一次报告覆盖写在 ``chapter.last_quality_report``，
``issues`` 经 ``sync_quality_debts`` 沉淀为「正文修复」导向的 ``QualityDebt``。
但系统**反复犯同一类低级错误**（境界偏差、前后不一致、凭空设定）的「为什么」无处可查：
到底是写章时该注入的设定没注入（context_missing），还是注入了模型没遵守（context_ignored），
还是章纲/设定库源头就错（outline_planning_error / setting_self_contradiction）。

本表把**每次质检中每一个低分项（维度 score<8 或一条 issue）逐条落库**，并由分析层补上
根因分类与「代码/管线层」修复建议，形成可跨章/跨次聚合的高频根因基线（台账→回灌）。
与 ``OutlineIssueLog`` 同构：持久化优先硬规则要求问题信号不能只停在章节 extra 里。
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class QualityRootCauseLog(Base):
    """单条质检低分项的根因记录（按 project + chapter + 指纹去重）。

    字段约定
    --------
    - ``item_kind``：``dimension``（某质检维度 score<8）/ ``issue``（一条 issues 条目）。
    - ``dimension``：维度键（如 ``realm_check`` / ``setting_consistency``）或 issue 的 type。
    - ``score``：维度原始分（issue 无分 → 空）。
    - ``root_cause_category``：分析层归一化根因，见 prompts/quality_root_cause_prompt.CATEGORIES。
    - ``code_fix_suggestion``：代码/管线层修复方向（改哪个文件/prompt/采样档），区别于正文微调。
    - ``evidence``：分析依据快照（注入了哪些设定、draft 调用是否存在、静态修复落点提示等）。
    - ``analysis_status``：``pending``（已落库待分析）/ ``analyzed`` / ``failed`` / ``dismissed``。
    """

    __tablename__ = "quality_root_cause_logs"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "chapter_id", "fingerprint",
            name="uq_quality_root_cause_project_chapter_fingerprint",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    chapter_id = Column(UUID(as_uuid=True), ForeignKey("chapters.id"), nullable=True)

    source_chapter_number = Column(Integer, nullable=False, default=0)  # 发现时章号（chapter_id 空时仍可用）
    run_id = Column(String(36), nullable=False, default="")            # 同一次质检的多条记录共享，便于成组回溯

    item_kind = Column(String(20), nullable=False, default="dimension")  # dimension / issue
    dimension = Column(String(60), nullable=False)                       # 维度键或 issue type
    score = Column(Integer, nullable=True)                               # 维度原始分（issue 为空）
    severity = Column(String(20), nullable=False, default="medium")      # low / medium / high
    problem_summary = Column(Text, nullable=False)                       # 低分项的具体描述/comment

    root_cause_category = Column(String(40), nullable=False, default="pending")  # 分析层归一化根因
    root_cause_detail = Column(Text)                                     # 根因解释（为什么会这样）
    code_fix_suggestion = Column(Text)                                   # 代码/管线层修复建议
    evidence = Column(JSONB, nullable=False, default=dict)              # 分析依据快照

    analysis_status = Column(String(20), nullable=False, default="pending")  # pending/analyzed/failed/dismissed
    fingerprint = Column(String(64), nullable=False)                    # 与 project+chapter 组成唯一键
    occurrence_count = Column(Integer, nullable=False, default=1)       # 同指纹累计命中次数

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    chapter = relationship("Chapter")
    project = relationship("Project")
