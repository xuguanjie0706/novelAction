"""WritingToolsMixin 组合壳 — 向后兼容的 re-export。

各能力实现见：
- writing_pre_warn.py   写前预警（pre_write_warning）
- writing_scene_plan.py 分场计划（scene_plan）
- writing_reader_sim.py 读者心理模拟（reader_psychology_sim）
"""
from __future__ import annotations

from app.services.ai.writing_pre_warn import PreWriteWarnMixin
from app.services.ai.writing_scene_plan import ScenePlanMixin
from app.services.ai.writing_reader_sim import ReaderPsychologyMixin


class WritingToolsMixin(PreWriteWarnMixin, ScenePlanMixin, ReaderPsychologyMixin):
    """组合三个写作工具 Mixin，保持与旧调用方 `self.pre_write_warning / scene_plan / reader_psychology_sim` 的接口兼容。"""
    pass
