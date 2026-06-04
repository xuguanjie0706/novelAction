"""
power_exception.py — 跨境破例预算（战力体系硬约束）

设计动机（战力崩坏根因之一）：
  网文里偶尔需要「低境界越阶击杀」作为爽点（如主角天生至尊骨），但若不设上限，
  AI 会临时发明各种体质/血脉/外挂来圆任意跨度的秒杀（斗者秒杀斗灵），导致战力体系崩坏。

机制：
  全书显式登记**有限的**破例依据，每条限定「最多跨几个大境」+「全书可用次数」。
  - 写章期：把预算注入正文硬约束，写手只能用已登记破例，且不得超剩余次数。
  - 质检期：把预算注入 realm_check，未登记的跨≥2大境碾压一律 realm_violation。

数据位置：Project.extra.power_exception_budget = [
  {"name": "至尊骨", "basis": "天生至尊骨，可越阶战斗", "max_span": 2, "budget": 3, "used": 0},
  ...
]
- max_span：允许跨几个「大境」（默认 2）
- budget：全书可用次数；used：已消耗次数
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified

EXTRA_KEY = "power_exception_budget"
# 跨「大境」阈值：跨度 ≥ 此值的击杀/碾压才需要破例授权（1 大境内属正常波动）。
CROSS_TIER_THRESHOLD = 2


def get_power_exception_budget(project: Any) -> list[dict]:
    extra = project.extra if isinstance(getattr(project, "extra", None), dict) else {}
    raw = extra.get(EXTRA_KEY)
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        out.append({
            "name": str(item.get("name"))[:60],
            "basis": str(item.get("basis") or "")[:200],
            "max_span": int(item.get("max_span") or CROSS_TIER_THRESHOLD),
            "budget": int(item.get("budget") or 0),
            "used": int(item.get("used") or 0),
        })
    return out


def build_power_exception_block(project: Any) -> str:
    """供写章/质检 prompt 注入的破例预算硬约束块。无登记时返回「零破例」铁律。"""
    budget = get_power_exception_budget(project)
    if not budget:
        return (
            "【跨境破例预算（战力体系硬约束）】\n"
            f"  本书未登记任何跨境破例：任何角色击败/秒杀高于自己 ≥{CROSS_TIER_THRESHOLD} 个大境的对手，"
            "一律视为战力崩坏，禁止出现；临时发明的体质/血脉/外挂不能作为越阶击杀的理由。"
        )
    lines = [
        "【跨境破例预算（战力体系硬约束）】",
        f"  全书仅允许下列已登记依据支撑「跨 ≥{CROSS_TIER_THRESHOLD} 大境」的越阶击杀/碾压，其余一律算战力崩坏：",
    ]
    for ex in budget:
        remaining = max(0, ex["budget"] - ex["used"])
        lines.append(
            f"  · {ex['name']}：依据={ex['basis'] or '（未填）'}；"
            f"最多跨 {ex['max_span']} 大境；全书限 {ex['budget']} 次，已用 {ex['used']} 次，剩余 {remaining} 次"
        )
    lines.append(
        "  ⚠️ 未登记的设定不得用于越阶击杀；即便已登记，超出「最多跨 N 大境」或「剩余次数」也算违规。"
    )
    return "\n".join(lines)


def consume_power_exception(project: Any, name: str, *, count: int = 1) -> bool:
    """消耗一条破例预算（used += count）。返回是否成功写入；调用方负责 commit。"""
    extra = dict(project.extra) if isinstance(getattr(project, "extra", None), dict) else {}
    raw = extra.get(EXTRA_KEY)
    if not isinstance(raw, list):
        return False
    changed = False
    for item in raw:
        if isinstance(item, dict) and str(item.get("name") or "") == name:
            item["used"] = int(item.get("used") or 0) + count
            changed = True
            break
    if changed:
        extra[EXTRA_KEY] = raw
        project.extra = extra
        flag_modified(project, "extra")
    return changed
