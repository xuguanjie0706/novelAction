"""
LLM 任务级采样配置（temperature / top_p / penalty）。

设计动机
========
此前 `_call_ai` / `_stream_ai` 仅传 `max_tokens`，所有任务（设定生成、章节起草、质检、复盘）
共用同一组默认采样参数。结果是：
  - 质检需要稳定 JSON 却用了高温 → 解析失败/字段抖动；
  - 章节正文需要文采变化却被默认温度收敛 → 千篇一律的"AI 味"。

本模块按任务类型给出 **保守而具备区分度的默认值**，调用方传入 `task` 字符串即可。
未识别的任务回退 `default`，且整段配置允许被 `None` 覆盖以保持旧行为兼容。

调用约定
========
- 数值型 prompt（境界数字、章节字数、JSON 解析）→ 低温度（0.2-0.4）+ 高 top_p；
- 创意型 prompt（章节正文、复盘叙事）→ 高温度（0.85-0.95）+ presence_penalty 抑制重复；
- 大纲规划/复盘提取等"半结构化任务"取中段（0.5-0.7）。

只暴露纯 dict，不引入 SDK 类型，便于不同 OpenAI 兼容网关自适应（部分网关不接受
`presence_penalty`，调用层会自动剔除空值）。
"""
from __future__ import annotations

from typing import Optional


# 任务名 → 采样参数。键命名遵循「域.动作」便于扩展（例：bootstrap.settings、draft.chapter）。
TASK_PROFILES: dict[str, dict] = {
    # ── 章节正文（创意型，需要文采变化）────────────────────────────
    "draft.chapter": {
        "temperature": 0.9,
        "top_p": 0.95,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.3,
    },
    "draft.opening": {
        # 开局期：钩子密度高，允许更跳脱
        "temperature": 0.95,
        "top_p": 0.95,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.4,
    },
    "draft.climax": {
        # 高潮期：情绪拉满
        "temperature": 0.95,
        "top_p": 0.97,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.4,
    },
    "draft.dark_hour": {
        # 至暗期：节奏放缓，需要克制不能太飘
        "temperature": 0.75,
        "top_p": 0.9,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
    },
    "draft.rising": {
        # 扩张期 / 起飞期：世界观推进需要一点稳定性，温度从 chapter 默认 0.9 降到 0.8
        "temperature": 0.8,
        "top_p": 0.92,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.3,
    },
    "draft.turning": {
        # 转折期：矛盾升级与代价兑现，需要重复关键意象/伏笔名词，降 frequency_penalty
        "temperature": 0.85,
        "top_p": 0.93,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.3,
    },
    "draft.ending": {
        # 收束期：留下一卷悬念种子，克制但不像 dark_hour 那么压抑
        "temperature": 0.8,
        "top_p": 0.92,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.25,
    },
    # ── 白话直白档（番茄纯爽文）────────────────────────────────────
    # 设计动机：plain 书追求"一看就懂"，与 draft.chapter 的"文采变化"取向冲突。
    #   · 低 temperature/top_p → 抑制生僻词与绕句，措辞回归大白话；
    #   · 近零 presence/frequency_penalty → 不惩罚重复，允许金手指名/境界/数值
    #     反复砸（番茄读者要的是重复强化，不是同义词替换）。
    # 所有 phase 共用此单档：plain 书"直白优先于阶段文采差异"，不再按开局/高潮分叉。
    "draft.plain": {
        "temperature": 0.7,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.0,
    },
    "dabai.write": {
        # 大白文专线：低温 + 低 penalty，按章节要素五拍稳定输出
        "temperature": 0.72,
        "top_p": 0.9,
        "frequency_penalty": 0.15,
        "presence_penalty": 0.0,
    },
    "suggest.stream": {
        # 写作建议：偏自由，但不要走偏
        "temperature": 0.8,
        "top_p": 0.92,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
    },
    # ── Bootstrap / 设定生成（半结构化）────────────────────────────
    "bootstrap.positioning": {
        # 立项会议：需要理性收敛到清晰定位
        "temperature": 0.55,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.0,
    },
    "bootstrap.fanfic_synopsis": {
        "temperature": 0.55,
        "top_p": 0.9,
        "frequency_penalty": 0.15,
        "presence_penalty": 0.0,
    },
    "bootstrap.project": {
        "temperature": 0.6,
        "top_p": 0.9,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.0,
    },
    "bootstrap.settings": {
        # 设定卡：偏稳定，避免胡乱发散
        "temperature": 0.65,
        "top_p": 0.9,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.0,
    },
    "bootstrap.power_systems": {"temperature": 0.6, "top_p": 0.9},
    "bootstrap.factions": {"temperature": 0.7, "top_p": 0.9},
    "bootstrap.storylines": {"temperature": 0.7, "top_p": 0.9},
    "bootstrap.storyline_weave": {"temperature": 0.3, "top_p": 0.85},
    "bootstrap.characters": {"temperature": 0.75, "top_p": 0.9},
    "bootstrap.skills": {"temperature": 0.65, "top_p": 0.9},
    "bootstrap.items": {"temperature": 0.65, "top_p": 0.9},
    "bootstrap.volumes": {"temperature": 0.6, "top_p": 0.9},
    "bootstrap.vol1_chapters": {
        # 第一卷章级大纲：半结构化生成，需要创意但要服从因果链约束
        "temperature": 0.65,
        "top_p": 0.9,
        "frequency_penalty": 0.15,
        "presence_penalty": 0.1,
    },
    "bootstrap.memory": {"temperature": 0.6, "top_p": 0.9},
    "bootstrap.relations": {"temperature": 0.65, "top_p": 0.9},
    "bootstrap.emotion_arc": {"temperature": 0.45, "top_p": 0.85},
    "bootstrap.villain_arc": {"temperature": 0.45, "top_p": 0.85},
    "bootstrap.narrative_arcs": {"temperature": 0.45, "top_p": 0.85},

    # ── 大纲规划 ────────────────────────────────────────────────
    "outline.full_structure": {"temperature": 0.55, "top_p": 0.9},
    "outline.expand": {"temperature": 0.7, "top_p": 0.9},
    "outline.character_gap": {"temperature": 0.55, "top_p": 0.9},
    "outline.repair": {
        # 大纲修复补丁：最小化改动任务，须在严格保留邻近章节连贯性的前提下做局部修正。
        # temperature 从 0.65 降至 0.45，防止 AI "发挥创意"偏离原有结构，
        # 引入新的一致性问题；presence_penalty 保留以抑制重复措辞。
        "temperature": 0.45,
        "top_p": 0.88,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1,
    },
    # ── 质检 / 一致性（要稳定 JSON 与可比较打分）────────────────
    "quality.micro_patch": {"temperature": 0.15, "top_p": 0.75},
    "quality.root_cause": {"temperature": 0.2, "top_p": 0.8},
    "quality.check": {
        "temperature": 0.2,
        "top_p": 0.8,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "quality.pre_write_warning": {
        "temperature": 0.2,
        "top_p": 0.8,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "quality.outline_check": {"temperature": 0.2, "top_p": 0.8},
    # ── 专项大纲质检（拆分自 outline_check，每个只检查一件事）────
    "quality.causality_check": {
        # 因果链审计：需要精确逻辑判断，温度极低
        "temperature": 0.15,
        "top_p": 0.75,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "quality.character_arc_check": {
        # 人物弧审计：需要一定叙事理解，稍高于因果链
        "temperature": 0.2,
        "top_p": 0.8,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "quality.foreshadow_audit": {
        # 伏笔审计：配对检查 + 主题判断，低温稳定
        "temperature": 0.15,
        "top_p": 0.75,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
    },
    "quality.coherence_check": {"temperature": 0.2, "top_p": 0.8},
    "quality.coherence_apply": {"temperature": 0.4, "top_p": 0.85},
    # ── 复盘 / 提取 ────────────────────────────────────────────
    "debrief.auto": {"temperature": 0.3, "top_p": 0.85},
    "debrief.extract_memory": {"temperature": 0.3, "top_p": 0.85},
    "debrief.foreshadow": {"temperature": 0.3, "top_p": 0.85},
    # ── 记忆库体检 ─────────────────────────────────────────────
    "memory.conflict_detect": {"temperature": 0.2, "top_p": 0.8},
    # ── 默认兜底 ───────────────────────────────────────────────
    "default": {},  # 空 dict 表示走 LLM 默认采样，与历史行为一致
}


def resolve_task_profile(task: Optional[str]) -> dict:
    """根据任务名返回采样参数；未识别返回空 dict。

    返回的 dict 仅包含 temperature/top_p/frequency_penalty/presence_penalty 这四个
    OpenAI 兼容协议公认字段，调用方在拼装 `chat.completions.create` 时直接 spread 即可。
    空值字段会被调用方剔除，避免某些网关报错。
    """
    if not task:
        return {}
    profile = TASK_PROFILES.get(task)
    if profile is None:
        return {}
    return {k: v for k, v in profile.items() if v is not None}


def phase_to_draft_task(phase: Optional[str], writing_style: Optional[str] = None) -> str:
    """卷阶段（phase）→ 章节起草任务名映射。

    阶段命名见 OutlineNode.phase 注释；未匹配则走通用 draft.chapter。

    Args:
        phase: 卷阶段标记（opening/rising/turning/dark_hour/climax/ending）。
        writing_style: 写作风格档位（plain/standard/dense）。``plain`` 时**优先级
            高于 phase**，统一返回低温的 ``draft.plain``——直白书要的是稳定的大白话，
            而非按阶段切换的文采差异。standard/dense 维持原有按 phase 分档逻辑。
    """
    if writing_style and str(writing_style).strip().lower() == "plain":
        return "draft.plain"
    if not phase:
        return "draft.chapter"
    p = str(phase).strip().lower()
    if p in ("opening", "开局期", "新手村"):
        return "draft.opening"
    if p in ("climax", "高潮期"):
        return "draft.climax"
    if p in ("dark_hour", "darkhour", "至暗期"):
        return "draft.dark_hour"
    if p in ("rising", "扩张期", "起飞期"):
        return "draft.rising"
    if p in ("turning", "转折期"):
        return "draft.turning"
    if p in ("ending", "收束期", "结局期"):
        return "draft.ending"
    return "draft.chapter"
