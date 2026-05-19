"""Bootstrap Step 11.5：全书跨卷核心谜题（伏笔预分配）。

设计动机
--------
当前伏笔是"走一步看一步"：AI 在每章大纲里临时决定埋什么伏笔。
这导致跨卷伏笔无法被系统层面追踪——写到第100章时，
AI 已经忘记第3章里埋过的细节，伏笔自然就断了。

本步骤在 Bootstrap 时预先规划5-8条跨卷级核心谜题，
每条谜题锚定三个章节：埋/加热/揭晓。
这些谜题是全书叙事结构的钢筋——其他内容是水泥，可以调整，
但钢筋一旦浇注就不该轻易移动。

产物
----
- Foreshadow 表：每条谜题创建一条 status=open 的记录
- Project.extra['core_mysteries']：完整列表，供前端展示和 AI 引用
- ctx['core_mysteries_summary']：摘要字符串，注入后续章纲 prompt
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.services.bootstrap.parse import parse_json

logger = logging.getLogger(__name__)


async def gen_core_mysteries(svc: Any, project, ctx: dict) -> list[dict]:
    """生成全书跨卷核心谜题并写 Foreshadow 表。

    Args:
        svc:     Bootstrap 服务实例（需要 _call_with_retry / db）。
        project: 当前项目模型。
        ctx:     全局 bootstrap 上下文（需要 volumes_summary / char_names /
                 chapter_quota_total / storyline_summary）。

    Returns:
        核心谜题列表，同时写入 Project.extra['core_mysteries']。
    """
    from app.models import Foreshadow

    system = (
        "你是有30年经验的网络小说总编辑，深知：好的伏笔是读者追更的隐形绳索。"
        "只返回 JSON 数组，不要任何解释文字。"
    )

    total_chapters = ctx.get("chapter_quota_total", 520)
    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    protagonist = ctx.get("protagonist", "主角")
    char_names = ctx.get("char_names", [])
    storyline_summary = ctx.get("storyline_summary", "（未设定）")
    positioning = ctx.get("positioning") or {}
    villain_arc_summary = ctx.get("villain_arc_summary", "（未设定）")

    prompt = f"""小说：《{ctx.get('project_title', '')}》（{ctx.get('genre', '')}）
主角：{protagonist}
全书总章数：{total_chapters}章
全体人物：{', '.join(char_names[:20]) or '（未设定）'}
故事线：{storyline_summary}
反派行动线：{villain_arc_summary}

【卷级骨架】
{volumes_summary}

作为总编辑，你正在为这部小说预置5-8条跨卷核心谜题。
这些谜题是全书叙事的「钢筋」——它们跨越多个卷，需要在全书范围内精确管理。

谜题类型：
- identity（身份之谜：主角/反派/配角的真实身份或来历）
- prophecy（预言之谜：某个预言或天命是否会应验）
- prop（道具之谜：某件法宝/古物的真正用途或来历）
- reversal（关系逆转：某段关系/阵营的真实性）
- hook（悬念钩子：某个重大事件的前因后果）

返回 JSON 数组：
[
  {{
    "name": "谜题代号（5字内，便于后续引用，如：主角身世之谜）",
    "mystery_type": "identity/prophecy/prop/reversal/hook",
    "description": "这个谜题是什么（读者看到的表象是什么，真相是什么，50字内）",
    "why_readers_care": "读者为什么要追着看这个谜题（情感或利益驱动，20字内）",
    "lay_chapter": 3,
    "lay_method": "如何在第X章埋下这个谜题（具体手法，30字内，必须是「看得见」的细节，不是旁白）",
    "heat_chapters": [15, 30, 50],
    "heat_methods": ["第15章加热手法", "第30章加热手法", "第50章加热手法"],
    "reveal_chapter": 80,
    "reveal_method": "如何揭晓（具体场景/手法，30字内）",
    "emotional_payoff": "揭晓时读者的情绪（震惊/感动/爽快/复仇/遗憾）"
  }}
]

【编辑铁律】
1. 必须有且至少1条 identity 类型（读者对人物身份的好奇是最持久的黏性）
2. lay_chapter 必须在前20章内（越早埋越好，给读者足够追更理由）
3. reveal_chapter 不得超过全书总章数的90%（留空间做情感收尾）
4. heat_chapters 至少3个，均匀分布在 lay 和 reveal 之间
5. 不同谜题的 reveal_chapter 不能都集中在同一卷（分散高潮）
6. lay_method 必须是具体可写的场景细节，禁止"暗示"/"隐约提到"这种废话
只返回JSON数组，不要解释。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=3000, task="bootstrap.core_mysteries"
        )
        mysteries = parse_json(raw)
        if not isinstance(mysteries, list):
            mysteries = []
    except Exception:
        mysteries = []

    # 写 Foreshadow 表（每条谜题一条记录）
    saved_mysteries: list[dict] = []
    for m in mysteries:
        name = (m.get("name") or "").strip()
        description = (m.get("description") or "").strip()
        if not name or not description:
            continue
        try:
            fs = Foreshadow(
                project_id=project.id,
                description=f"【核心谜题】{name}：{description}",
                laid_chapter_number=m.get("lay_chapter"),
                planned_resolve_chapter=m.get("reveal_chapter"),
                status="open",
                foreshadow_type=m.get("mystery_type", "hook"),
                extra={
                    "mystery_name": name,
                    "why_readers_care": m.get("why_readers_care", ""),
                    "lay_method": m.get("lay_method", ""),
                    "heat_chapters": m.get("heat_chapters", []),
                    "heat_methods": m.get("heat_methods", []),
                    "reveal_method": m.get("reveal_method", ""),
                    "emotional_payoff": m.get("emotional_payoff", ""),
                    "is_core_mystery": True,
                    "heat_log": [],
                },
            )
            svc.db.add(fs)
            saved_mysteries.append({**m, "_foreshadow_id": None})  # id after flush
        except Exception:
            logger.exception("核心谜题写 Foreshadow 表失败（name=%s）", name)

    try:
        svc.db.flush()
    except Exception:
        logger.exception("核心谜题 flush 失败")

    # 写 Project.extra
    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "core_mysteries": mysteries}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        pass

    # ctx 摘要
    if mysteries:
        ctx["core_mysteries"] = mysteries
        ctx["core_mysteries_summary"] = "、".join(
            f"{m.get('name', '?')}(埋第{m.get('lay_chapter','?')}章→揭第{m.get('reveal_chapter','?')}章)"
            for m in mysteries[:6]
        )

    return mysteries
