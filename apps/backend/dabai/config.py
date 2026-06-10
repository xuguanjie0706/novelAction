"""大白文 bootstrap 配置。

集中管理：链路顺序、采样温度、卷/章规模、LLM 连接（环境变量）。
本分支不读主仓库任何配置，保持完全独立。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ── 链路顺序（编排器按此串行执行；--stop-after 可截断）──────────────────────────
PIPELINE_STEPS: list[str] = [
    "benchmark",         # 对标分析（找对标书 + 抽文笔/设定特征，全链注入）
    "positioning",       # 立项定位
    "golden_finger",     # 金手指外挂（大白文爽点引擎）
    "power_ladder",      # 境界阶梯
    "factions",          # 势力阵营
    "characters",        # 人物档案
    "storylines",        # 故事线
    "story_assets",      # 剧情资产+初始关系（台账种子：争夺点/底牌/成长线 + 关系张力）
    "volumes",           # 卷骨架
    "chapter_outlines",  # 章纲（爽点节拍器）
]

# ── 任务级采样温度（爽文要稳定结构 + 一点跳脱，整体低于精品文）────────────────
STEP_TEMPERATURE: dict[str, float] = {
    "benchmark": 0.4,    # 对标分析要稳，少幻觉
    "positioning": 0.5,
    "golden_finger": 0.7,
    "power_ladder": 0.4,
    "factions": 0.6,
    "characters": 0.7,
    "storylines": 0.6,
    "story_assets": 0.65,
    "volumes": 0.6,
    "chapter_outlines": 0.75,  # 爽点要变化，但骨架仍需稳定 JSON
}
DEFAULT_TEMPERATURE = 0.6


@dataclass
class DabaiConfig:
    """一次 bootstrap 运行的全部可调参数。"""

    logline: str = ""
    # 规模
    volume_count: int = 6           # 第一版卷数（卷骨架步会生成这么多卷）
    volume_chapters: int = 30       # 每卷章数（章纲步展开这么多章）
    chapter_batch_size: int = 30    # 章纲分批大小（每批一次 LLM 调用，支持大卷、规避 token 上限）
    first_volume_only: bool = True  # 章纲默认只展开第 1 卷（懒展开，省 token）
    # 大白文调性
    shuang_pool: list[str] = field(default_factory=lambda: [
        "打脸", "升级", "获宝", "扮猪吃虎", "装逼", "群嘲反转", "收小弟", "救场", "扬名",
    ])
    big_beat_every: int = 5         # 每 N 章一个大爆点（强度阶梯）
    golden_chapters: int = 3        # 黄金 N 章必有强爽点
    max_new_info_per_chapter: int = 2  # 单章信息密度上限
    # LLM 连接
    base_url: str = field(default_factory=lambda: os.getenv("DABAI_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("DABAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("DABAI_MODEL", "gpt-4o-mini"))
    mock: bool = False              # True=离线 mock，不调真实 LLM
    stop_after: str | None = None   # 跑到某步即停（含该步）
    max_tokens: int = 8192

    def temperature_for(self, step: str) -> float:
        return STEP_TEMPERATURE.get(step, DEFAULT_TEMPERATURE)

    def active_steps(self) -> list[str]:
        """根据 stop_after 截断链路。"""
        if not self.stop_after or self.stop_after not in PIPELINE_STEPS:
            return list(PIPELINE_STEPS)
        idx = PIPELINE_STEPS.index(self.stop_after)
        return PIPELINE_STEPS[: idx + 1]
