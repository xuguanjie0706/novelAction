"""大白文 bootstrap 配置。

集中管理：链路顺序、采样温度、卷/章规模、LLM 连接（环境变量）。
本分支不读主仓库任何配置，保持完全独立。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ── 链路顺序（编排器按此串行执行；--stop-after 可截断）──────────────────────────
# 按次计费合并（2026-06-12 五批）：合并步一次 LLM 调用产出本组所有键（_MERGE_CARRIERS），
# derived 步不再单独调用。设定链 9 次 → 6 次；章纲默认单次出 beat+五拍（见 chapter_outlines）。
PIPELINE_STEPS: list[str] = [
    "benchmark",          # ★合并调用①★ 对标分析 + 立项定位
    "positioning",        #   ↑derived（随 benchmark 一次产出）
    "golden_finger",      # ★合并调用②★ 金手指 + 境界阶梯 + 卷级反派阶梯（力量与对立面同域）
    "power_ladder",       #   ↑derived
    "antagonist_ladder",  #   ↑derived（Boss 档与境界档同次推理，对齐性更好）
    "factions",           # ★合并调用③★ 势力（含场景池）+ 人物（Boss 建档 + 配角池 + speech_kit）
    "characters",         #   ↑derived
    "storylines",         # ★合并调用④★ 叙事规划三块：故事线 + 剧情资产/关系 + 谜题排程
    "story_assets",       #   ↑derived
    "mystery_schedule",   #   ↑derived（谜题与故事线/资产同次推理，咬合更紧）
    "volumes",            # ★调用⑤★ 卷骨架（接住 Boss/资产/谜题/故事线节点）
    "title_blurb",        # ★调用⑥★ 书名海选 + 简介（后置：可引用卷 Boss/大爆点；独立保 0.85 温度档）
    "chapter_outlines",   # 章纲：默认 volume_chapters 单次出 beat+五拍；超大卷/失败降级两段式
]

# ── 任务级采样温度（爽文要稳定结构 + 一点跳脱，整体低于精品文）────────────────
STEP_TEMPERATURE: dict[str, float] = {
    "benchmark": 0.4,    # 对标分析要稳，少幻觉
    "positioning": 0.5,
    "golden_finger": 0.65,  # 合并步：金手指要跳脱、境界/反派要稳，折中
    "power_ladder": 0.4,
    "antagonist_ladder": 0.55,
    "factions": 0.6,
    "characters": 0.7,
    "storylines": 0.6,       # 合并步：三块叙事规划共用
    "story_assets": 0.65,
    "mystery_schedule": 0.5,
    "title_blurb": 0.85,     # 书名要跳脱（独立成步的原因：与 volumes 0.6 温度冲突）
    "volumes": 0.6,
    "volume_chapters": 0.7,  # 单次出 beat+五拍：介于规划 0.6 与展开 0.75 之间
    "beat_sequence": 0.6,    # 降级路径：全局节拍规划
    "chapter_outlines": 0.75,  # 降级路径：分批五拍展开
    "chapter_repair": 0.4,     # 定向修复：只修不创
}
DEFAULT_TEMPERATURE = 0.6


@dataclass
class DabaiConfig:
    """一次 bootstrap 运行的全部可调参数。"""

    logline: str = ""
    # 规模
    volume_count: int = 6           # 第一版卷数（卷骨架步会生成这么多卷）
    volume_chapters: int = 30       # 每卷规划章数（卷骨架 planned_chapters）
    outline_expand_size: int = 15   # 单次章纲展开窗口（建书/补全各最多这么多个；30 章卷=展开 2 次）
    chapter_batch_size: int = 5     # 窗口内五拍 LLM 批大小（15 章窗=3 批）
    beat_chunk_size: int = 60       # 【降级路径】节拍序列单次调用最大章数
    single_call_max_chapters: int = 8   # >8 章强制两段式（beat 规划 + 小批五拍，质量优于单次整卷）
    repair_rounds: int = 1          # linter 问题定向修复轮数（0=关闭闭环；lint 干净时 0 次调用）
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
    max_tokens: int = 30000         # 单次输出上限（volume_chapters 整卷 beat+五拍约 9-15k token）

    def temperature_for(self, step: str) -> float:
        return STEP_TEMPERATURE.get(step, DEFAULT_TEMPERATURE)

    def outline_window_end(self, vol_planned: int, start_chapter: int = 1) -> int:
        """本趟章纲展开在卷内的结束章号（含）。例：30 章卷、窗口 15、从 16 起 → 30。"""
        start = max(1, int(start_chapter))
        size = max(1, int(self.outline_expand_size))
        return min(start + size - 1, max(start, int(vol_planned)))

    def active_steps(self) -> list[str]:
        """根据 stop_after 截断链路。"""
        if not self.stop_after or self.stop_after not in PIPELINE_STEPS:
            return list(PIPELINE_STEPS)
        idx = PIPELINE_STEPS.index(self.stop_after)
        return PIPELINE_STEPS[: idx + 1]
