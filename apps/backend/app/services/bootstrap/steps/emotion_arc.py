"""Bootstrap Step 9.5：全书情绪节律图。

设计动机
--------
纯靠 phase 阶段标记（opening/rising/climax 等）能约束节奏类型，
但管不住"全书情绪账户"——一部小说如果连续6卷都只是爽感输出，
读者会审美疲劳；如果连续3卷都是压抑，读者会弃书。

本步骤在卷骨架确定后，用总编辑视角为每一卷分配"情绪收支"：
  emotional_deposit  → 读者这一卷的情绪收益（爽感/感动/悬疑满足）
  emotional_cost     → 读者这一卷的情绪消耗（虐/焦虑/紧张）
  net_balance        → 净余额方向：positive/neutral/negative
  dominant_emotion   → 本卷主色调

结果写入 Project.extra['emotion_arc']，并以摘要形式存入 ctx，
供 vol1_chapter_plans / vol_chapter_plans 的 editorial_prompt_block 引用。
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.bootstrap.narrative_arc_gen import (
    call_json_array_with_retry,
    persist_extra_arc,
)

logger = logging.getLogger(__name__)


async def gen_emotion_arc(
    svc: Any,
    project,
    ctx: dict,
    *,
    persist: bool = True,
) -> list[dict]:
    """为每一卷生成情绪收支预算，确保全书情绪节律有起伏有落地。

    Args:
        svc:     Bootstrap 服务实例（需要 _call_with_retry / db）。
        project: 当前项目模型。
        ctx:     全局 bootstrap 上下文。

    Returns:
        情绪节律列表，每卷一条 dict，同时写入 Project.extra['emotion_arc']。
    """
    system = (
        "你是有30年经验的网络小说总编辑，专注读者心理与长篇留存率研究。"
        "只返回 JSON 数组，不要任何解释文字。"
    )

    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    positioning = ctx.get("positioning") or {}
    tropes = "、".join(positioning.get("tropes", []))
    emotional_arc_setting = positioning.get("emotional_arc", "medium")
    pace_type = positioning.get("pace_type", "medium")

    prompt = f"""小说：《{ctx.get('project_title', '')}》（{ctx.get('genre', '')}）
主角：{ctx.get('protagonist', '主角')}
核心爽点：{tropes or '（未设定）'}
感情线占比设定：{emotional_arc_setting}
节奏类型：{pace_type}

【卷级骨架】
{volumes_summary}

你是总编辑，正在为这部小说制定全书情绪节律图。
读者是有「情绪账户」的：爽感/感动/悬疑满足感是存入，虐主/焦虑/紧张是支出。
长期高消耗无补充 → 弃书；长期无消耗 → 审美疲劳。

请为每一卷分配情绪收支，返回JSON数组（顺序与卷骨架一致）：
[
  {{
    "vol_index": 0,
    "vol_title": "卷名（与骨架一致）",
    "phase": "opening",
    "dominant_emotion": "主色调（exciting/warm/tense/epic/sad/mysterious/romantic，单选）",
    "emotional_deposit": "读者本卷的情绪收益（具体：几次爽点/感动/悬疑满足，各20字内）",
    "emotional_cost": "读者本卷的情绪消耗（虐主次数/焦虑密度/紧张程度，20字内；若无虐主填'轻微紧张'）",
    "net_balance": "positive/neutral/negative（正=收益>消耗，负=消耗>收益）",
    "arc_note": "总编辑批注：本卷情绪设计的关键决策（30字内，如'必须在第X章给读者情感出口以抵消前段压抑'）"
  }}
]

【编辑铁律】
1. 连续3卷 net_balance=negative 必须有1卷 positive 穿插——否则强制调整
2. climax/ending 卷必须是 positive（伏笔回收带来的满足感是最大收益）
3. dark_hour 卷可以是 negative，但 dominant_emotion 不能全是 sad，需混入 tense/mysterious
4. opening 卷必须是 positive（新读者第一印象决定追读率）
5. 全书至少1卷以 romantic 或 warm 为主色调（感情线或兄弟情收益）
只返回JSON数组，不要解释。"""

    arc = await call_json_array_with_retry(
        svc, system, prompt, task="bootstrap.emotion_arc",
    )

    if persist:
        persist_extra_arc(svc, project, "emotion_arc", arc)

    # ctx 摘要（供章纲 prompt 引用）
    if arc:
        ctx["emotion_arc"] = arc
        parts = []
        for i, v in enumerate(arc):
            title = v.get("vol_title") or f"卷{v.get('vol_index', i)}"
            parts.append(f"{title}({v.get('net_balance','?')},{v.get('dominant_emotion','?')})")
        ctx["emotion_arc_summary"] = " | ".join(parts)

    return arc
