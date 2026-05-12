"""全书字数硬约束 prompt 片段。

把 `target_words` 翻译成「类型与篇幅」自然语言约束，注入 premise 生成 prompt，
避免 LLM 默认套用 300-500 万字的网文超长篇区间。
"""

from __future__ import annotations


def book_length_constraints_for_prompt(target_words: int) -> str:
    """写入 LLM：premise「类型与篇幅」必须与项目 target_words 一致，避免默认套用网文超长篇区间。"""
    from app.services.outline_planning import words_to_plan

    tw = max(1, int(target_words or 1_200_000))
    plan = words_to_plan(tw)
    approx_wan = round(tw / 10_000)
    return (
        f"【全书字数目标（硬性约束）】全书计划总字数为 {tw:,} 字（约 {approx_wan} 万字），"
        f"按当前规划约 {plan['total_chapters']} 章、{plan['total_volumes']} 卷。\n"
        "premise 中的「类型与篇幅」必须与上述总字数一致：用该字数规模（或与之等价的单一区间，且上下限均不得偏离该目标一个数量级）描述篇幅，"
        "禁止写「三百万—五百万字」「数百万字」「千万字级」等与上述目标明显矛盾的常见超长篇口径；"
        "若题材常见于超长篇，仍须按本项目既定总字数收敛叙事尺度（地图换代、支线数量与之匹配），不得暗示必须写到更高字数才能讲完。"
    )
