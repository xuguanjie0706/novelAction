"""dabai 实验书架 — 技能/道具详细规格（用法·代价·进阶·限制）锁定与注入。

设计动机（2026-06-14）：
  写前导演单原本只锁境界/位置/在场/五拍，不锁关键功法·法宝的「怎么用、什么代价、
  怎么进阶」。分场与正文遇到金手指技能或法宝时只能即兴编（能力漂移、前后矛盾的主因）。
  本模块让导演单在功法/道具首次登场或被使用的那一章，一次性把规格锁进资产台账
  （``DabaiAsset.spec``），随后：① 同章经导演单简报注入分场/正文；② 后续章节经
  ``build_ledger_block`` 沿用，保证全书用法一致；③ 台账 tab 可查询。

与 ``lab_ledger`` 分工：ledger 管「持有什么/状态」，本模块管「规格设定细节」。
为避免与 lab_ledger 循环导入，build_ledger_block 侧以函数级 import 调用本模块。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.dabai import DabaiChapterOutline, DabaiProject
from app.models.dabai_lab import DabaiAsset
from app.services.dabai.lab_ledger import (
    _GRADE_LABELS, _ASSET_KINDS, _KIND_LABELS, _is_noise_asset, protagonist_name,
)

logger = logging.getLogger(__name__)

# 规格四要素：注入与展示统一口径
SPEC_FIELDS = ("usage", "cost", "progression", "restriction")
SPEC_LABELS = {
    "usage": "用法", "cost": "代价", "progression": "进阶", "restriction": "限制",
}
_FIELD_MAXLEN = 160


def coerce_spec(raw: object) -> dict | None:
    """把 LLM 产出的 spec 规整为 {usage/cost/progression/restriction} 字符串字典。

    至少有一个非空字段才返回 dict；全空返回 None（不落库空壳）。
    """
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for key in SPEC_FIELDS:
        val = raw.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if text:
            out[key] = text[:_FIELD_MAXLEN]
    return out or None


def merge_spec(existing: object, incoming: dict) -> tuple[dict, bool]:
    """合并规格：仅补全既有为空的字段，已锁定的字段保持不变（设定稳定性优先）。

    Returns:
        (合并后字典, 是否有新增字段)。
    """
    base: dict[str, str] = dict(existing) if isinstance(existing, dict) else {}
    changed = False
    for key in SPEC_FIELDS:
        new_val = incoming.get(key)
        if new_val and not str(base.get(key) or "").strip():
            base[key] = str(new_val)[:_FIELD_MAXLEN]
            changed = True
    return base, changed


def format_spec_inline(spec: object) -> str:
    """规格字典 → 单行「用法：…｜代价：…｜进阶：…｜限制：…」；空规格返回空串。"""
    if not isinstance(spec, dict):
        return ""
    segs = [
        f"{SPEC_LABELS[k]}：{str(spec[k]).strip()}"
        for k in SPEC_FIELDS
        if str(spec.get(k) or "").strip()
    ]
    return "｜".join(segs)


def _asset_spec_line(a: DabaiAsset) -> str:
    grade = f"[{_GRADE_LABELS[a.grade]}]" if a.grade is not None else ""
    body = format_spec_inline(a.spec)
    if not body:
        return ""
    return f"  · {a.name}{grade}（{_KIND_LABELS.get(a.kind or 'item', '道具')}）：{body}"


def build_locked_spec_block(db: Session, project: DabaiProject, ch: DabaiChapterOutline) -> str:
    """已锁定规格注入块：主角 active 且已有 spec 的功法/道具/金手指。

    用于导演单 prompt（让导演单沿用而非重新发明）+ 经 ledger_block 透传给分场/正文。
    无任何已锁定规格时返回空串。
    """
    protag = protagonist_name(project)
    rows = (
        db.query(DabaiAsset)
        .filter(
            DabaiAsset.project_id == project.id,
            DabaiAsset.status == "active",
            DabaiAsset.spec.isnot(None),
        )
        .order_by(DabaiAsset.kind, DabaiAsset.acquired_chapter)
        .limit(8)
        .all()
    )
    lines = [
        _asset_spec_line(a) for a in rows
        if (a.owner or protag) == protag and format_spec_inline(a.spec)
    ]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    return (
        "【已锁定技能/道具规格（既定设定，正文必须照此用法·代价·进阶写，禁止另编）】\n"
        + "\n".join(lines)
    )


def apply_asset_specs(
    db: Session,
    project: DabaiProject,
    ch: DabaiChapterOutline,
    specs: object,
    protag: str | None = None,
) -> list[str]:
    """把导演单产出的 asset_specs 落库到资产台账（upsert，不 commit）。

    - 已存在资产：补全空规格字段（已锁定字段不覆盖）。
    - 不存在且本章登场：建 active 资产行（source=prewarn）连同规格落库，
      便于台账即时可查 + 后续章节沿用；获得状态由复盘最终维护。

    Returns:
        变更摘要列表（供 SSE / 日志）。
    """
    if not isinstance(specs, list):
        return []
    protag = protag or protagonist_name(project)
    gf_name = str((project.golden_finger or {}).get("name") or "").strip()
    logs: list[str] = []
    for raw in specs[:8]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()[:120]
        if not name or _is_noise_asset(name):
            continue
        spec = coerce_spec(raw)
        if not spec:
            continue
        kind = str(raw.get("kind") or "item").lower()
        if kind not in _ASSET_KINDS:
            kind = "item"
        if kind == "golden_finger" and gf_name and name != gf_name:
            kind = "skill"
        owner = str(raw.get("owner") or protag).strip()[:100]
        row = (
            db.query(DabaiAsset)
            .filter(
                DabaiAsset.project_id == project.id,
                DabaiAsset.name == name,
                DabaiAsset.owner == owner,
            )
            .first()
        )
        if row:
            merged, changed = merge_spec(row.spec, spec)
            if changed:
                row.spec = merged
                logs.append(f"补全规格：{name}")
            continue
        db.add(DabaiAsset(
            project_id=project.id, kind=kind, name=name, owner=owner,
            description=(spec.get("usage") or "")[:300],
            acquired_chapter=ch.chapter_number, status="active",
            source="prewarn", spec=spec,
        ))
        logs.append(f"锁定规格：{name}")
    return logs
