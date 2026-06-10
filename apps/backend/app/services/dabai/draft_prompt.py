"""dabai 写作 prompt（主链路 Project/Chapter + OutlineNode.extra.dabai）。"""
from __future__ import annotations

from app.models import Chapter, OutlineNode, Project
from app.services.dabai.neo4j_sync import build_graph_context_block
from app.services.dabai.outline_plan import chapter_display_number


def _dabai_elements(plan: OutlineNode | None) -> dict:
    extra = (plan.extra if plan else {}) or {}
    dabai = extra.get("dabai") or {}
    if not isinstance(dabai, dict):
        dabai = {}
    return dabai


def build_dabai_chapter_elements_block(plan: OutlineNode | None) -> str:
    """格式化 UI「章节要素」五拍，供正文 prompt 硬约束。"""
    if not plan:
        return "（未找到章纲；按章节标题自行发挥，仍须五拍结构。）"
    dabai = _dabai_elements(plan)
    witnesses = dabai.get("witnesses") or []
    if isinstance(witnesses, list):
        witness_text = "、".join(str(w) for w in witnesses if w) or "围观众人"
    else:
        witness_text = str(witnesses) or "围观众人"
    end_hook = (
        (plan.highlight or "").strip()
        or (plan.hook or "").strip()
        or str(dabai.get("end_hook") or "").strip()
    )
    lines = [
        f"  爽点类型：{dabai.get('shuang_type', '')}",
        f"  ①憋屈（yaqu_setup）：{dabai.get('yaqu_setup', '')}",
        f"  ②转折扳机（emotion_turn）：{dabai.get('emotion_turn', '') or '（按章纲自行设计一个触发点）'}",
        f"  ③引爆（yinbao）：{dabai.get('yinbao', '')}",
        f"  ④爽点（shuang_payoff，须有见证者）：{dabai.get('shuang_payoff', '')}（见证者：{witness_text}）",
        f"  ⑤章末钩子（end_hook）：{end_hook}",
    ]
    realm = (plan.extra or {}).get("realm_rank")
    loc = (plan.extra or {}).get("location_name")
    if realm:
        lines.append(f"  境界档：第{realm}档")
    if loc:
        lines.append(f"  地点：{loc}")
    return "\n".join(lines)


def build_dabai_draft_prompt(
    project: Project,
    chapter: Chapter,
    plan: OutlineNode | None,
    *,
    prev_chapter_tail: str = "",
    user_prompt: str = "",
    replace_existing: bool = False,
) -> tuple[str, str]:
    """构造 dabai 正文 (system, user) prompt；必须逐项落实章节要素五拍。"""
    extra = (plan.extra if plan else {}) or {}
    gf = (project.extra or {}).get("golden_finger") or {}
    pos = (project.extra or {}).get("positioning") or {}
    target = int((plan.expected_words if plan else None) or 2000)
    hi = target + 200
    lo = max(1600, target - 200)
    ch_no = chapter_display_number(chapter)

    system = (
        "你是番茄/七猫玄幻修仙大白文写手。硬要求：\n"
        "1. 大白话、短句、对话多、节奏快，一看就懂；\n"
        "2. 必须按【本章爽点节拍（章节要素）】五拍顺序写，不得跳过或合并成一段糊过去；\n"
        "3. 情绪反转须有转折拍铺垫；见证者反应分级递进（愣→疑→惊→服）；\n"
        f"4. 篇幅：正文 {lo}～{hi} 字，严禁超过 {hi} 字；五拍各用紧凑篇幅，禁止重复铺陈；\n"
        "5. 只输出正文，不要标题、不要小标题、不要旁白说明。"
    )

    graph_block = build_graph_context_block(str(project.id))
    beat_block = build_dabai_chapter_elements_block(plan)

    user_parts = [
        f"《{project.title}》第{ch_no}章",
        f"金手指：{gf.get('name', '')}（{gf.get('core_ability', '')}）",
    ]
    if graph_block.strip():
        user_parts.append(graph_block.strip())

    user_parts.append("【本章爽点节拍（章节要素，必须逐项落实）】")
    user_parts.append(beat_block)

    if prev_chapter_tail.strip():
        tail = prev_chapter_tail.strip()[-400:]
        user_parts.append(
            f"【上章结尾（须紧接下一瞬间续写）】\n{tail}"
        )

    task = (
        f"按上面五拍写出第{ch_no}章正文。"
        f"目标 {target} 字（允许 {lo}～{hi}），严禁超过 {hi} 字。"
        "推进顺序：①憋屈（别拖太长）→ ②转折扳机（一两句过渡）→ ③引爆 → "
        "④爽点+见证者分级反应 → ⑤落在章末钩子上。直接开写正文。"
    )
    if replace_existing:
        task = "【整章重写】" + task + "不要复述旧稿套话；以章节要素为准。"
    user_parts.append(task)

    if user_prompt.strip():
        user_parts.append(f"【作者补充】{user_prompt.strip()}")

    if pos.get("taboo_lines"):
        tabs = pos.get("taboo_lines")[:3]
        if isinstance(tabs, list):
            user_parts.append(f"禁忌：{'；'.join(str(t) for t in tabs)}")

    return system, "\n\n".join(user_parts)
