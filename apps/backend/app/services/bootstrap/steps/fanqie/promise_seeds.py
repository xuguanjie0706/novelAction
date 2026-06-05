"""Bootstrap Fanqie Phase F：追读承诺种子（合并步骤）。

原两步（core_mysteries → opening_contract）合并为一次 LLM 调用。

设计动机
--------
对番茄读者来说，「核心谜题」和「开局追读承诺」本质上回答的是同一个问题：
「第一章结束后我为什么要点击下一章？」
前者是悬念维度（身世/外挂来源/隐藏身份），后者是承诺维度（期待/爽点预告）。
分两次调用时内容高度重叠，合并后 AI 可以对齐两者的叙事锚点，减少1次调用。

产物（与原两步完全兼容）
-----------------------
- Foreshadow 表：每条谜题一条记录
- Project.extra['core_mysteries']
- Project.extra['opening_contract']
- ReaderPromise 表：章末承诺种子
- ctx['core_mysteries_summary'], ctx['opening_contract']
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from app.models import Project
from app.services.bootstrap.opening_contract_io import BOOTSTRAP_OPENING_ORIGIN
from app.services.bootstrap.reader_promise_seed import seed_reader_promises
from app.services.bootstrap.steps.fanqie._json_once import call_fanqie_json_once

logger = logging.getLogger(__name__)

_STEP = "promise_seeds"


def _validate_promise_seeds(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "须为 JSON 对象"
    mysteries = data.get("core_mysteries")
    if not isinstance(mysteries, list) or len(mysteries) < 2:
        return "core_mysteries 至少需要 2 条谜题"
    oc = data.get("opening_contract")
    if not isinstance(oc, dict):
        return "opening_contract 须为对象"
    if not (oc.get("chapter1_end_hook") or oc.get("first_mystery_hook")):
        return "opening_contract 缺少关键钩子字段"
    return None


async def gen_promise_seeds(svc: Any, project: Project, ctx: dict) -> dict:
    """
    一次调用生成番茄版核心谜题（3-4条）+ 开局追读承诺，并持久化到 DB。

    @returns dict 含 core_mysteries 列表 + opening_contract 字典
    """
    system = (
        "你是番茄小说总编辑，深知读者追更的核心驱动是「悬念+爽感预告」。"
        "只返回 JSON，不要解释文字。"
    )
    fanqie_pos = ctx.get("fanqie_positioning") or {}
    gf = ctx.get("golden_finger") or {}
    fsm = ctx.get("face_slap_map") or {}
    volumes_summary = ctx.get("volumes_summary", "（未设定）")
    protagonist = ctx.get("protagonist", "主角")
    total_chapters = ctx.get("chapter_quota_total", 400)

    prompt = f"""小说：《{ctx['project_title']}》
类型公式：{fanqie_pos.get('genre_archetype', '')}
主角：{protagonist}
金手指：{gf.get('finger_name', '')}（{gf.get('mechanism', '')[:80]}）
金手指来源之谜：{gf.get('activation_trigger', '')}
打脸升级路径：{fsm.get('escalation_path', '')}
全书总章数预估：{total_chapters}章
卷骨架摘要：{(volumes_summary or '')[:300]}

作为总编辑，设计「读者留存双保险」：
1. 核心谜题：让读者追着看的「悬念绳索」（3-4条，覆盖全书）
2. 开局追读承诺：第一章结束时读者必须点下一章的理由

返回 JSON：
{{
  "core_mysteries": [
    {{
      "name": "谜题代号（5字内，如：主角身世之谜）",
      "mystery_type": "identity（身份）/origin（来历）/reversal（关系逆转）/hook（事件悬念）",
      "description": "表象是什么，真相是什么（40字内）",
      "why_readers_care": "读者为什么追这个谜题（情感驱动，20字内）",
      "lay_chapter": 3,
      "lay_method": "如何在第X章埋下（具体可写的场景细节，25字内）",
      "heat_chapters": [10, 25, 50],
      "reveal_chapter": 80,
      "emotional_payoff": "揭晓时读者的情绪（震惊/爽快/感动/遗憾）"
    }},
    {{同上，第2条}},
    {{同上，第3条（可选第4条）}}
  ],
  "opening_contract": {{
    "chapter1_end_hook": "第一章最后一句话/画面（让读者必须点下一章的钩子，20字内，必须具体）",
    "first_mystery_hook": "前3章内给读者埋下的最大悬念钩子（一句话，读者会问'这是为什么？'）",
    "power_expectation": "金手指激活后读者期待看到的第一个大爽点（一句话，画面感强）",
    "face_slap_tease": "第3-5章内的首次打脸预告（让读者看第一章就知道爽感要来了，20字内）",
    "chapter_end_promises": [
      {{"chapter": 1, "promise": "第1章章末给读者的承诺/钩子（一句话）", "promise_type": "chapter_ending"}},
      {{"chapter": 3, "promise": "第3章章末（首次打脸后）给的下一个期待", "promise_type": "chapter_ending"}},
      {{"chapter": 5, "promise": "第5章章末悬念种子", "promise_type": "chapter_ending"}}
    ]
  }}
}}

铁律：
1. core_mysteries 必须有至少1条 identity 类型
2. lay_chapter 必须在前15章内（番茄读者等不到第15章才看到谜题）
3. opening_contract 的所有描述必须是「第一章就能看到」的内容，不接受「后来会看到」
4. chapter1_end_hook 必须是「画面/动作」而非「心理描写」
5. 只返回 JSON"""

    data = await call_fanqie_json_once(
        svc,
        step=_STEP,
        system=system,
        prompt=prompt,
        task="bootstrap.opening_contract",
        validate=_validate_promise_seeds,
    )

    mysteries: list[dict] = data.get("core_mysteries") or []
    contract: dict = data.get("opening_contract") or {}

    # ── 写 Foreshadow 表 ───────────────────────────────────
    _persist_mysteries(svc, project, mysteries)

    # ── 写 opening_contract ────────────────────────────────
    _persist_opening_contract(svc, project, contract)

    # ── 写 ReaderPromise 种子 ──────────────────────────────
    promise_entries = _build_promise_entries(contract)
    if promise_entries:
        seed_reader_promises(svc, project, promise_entries, origin=BOOTSTRAP_OPENING_ORIGIN)

    # ── ctx 注入 ───────────────────────────────────────────
    if mysteries:
        ctx["core_mysteries"] = mysteries
        ctx["core_mysteries_summary"] = "、".join(
            f"{m.get('name', '?')}(埋第{m.get('lay_chapter','?')}章→揭第{m.get('reveal_chapter','?')}章)"
            for m in mysteries[:4]
        )
    if contract:
        ctx["opening_contract"] = contract

    return data


# ── 持久化辅助 ─────────────────────────────────────────────


def _persist_mysteries(svc: Any, project: Project, mysteries: list[dict]) -> None:
    """写 Foreshadow 表 + Project.extra['core_mysteries']。"""
    from app.models import Foreshadow

    for m in mysteries:
        name = (m.get("name") or "").strip()
        description = (m.get("description") or "").strip()
        if not name or not description:
            continue
        try:
            fs = Foreshadow(
                project_id=project.id,
                title=name[:200],
                description=f"【核心谜题】{name}：{description}",
                planned_resolve_chapter=m.get("reveal_chapter"),
                status="open",
                foreshadow_type=m.get("mystery_type", "hook"),
                extra={
                    "mystery_name": name,
                    "planned_lay_chapter": m.get("lay_chapter"),
                    "why_readers_care": m.get("why_readers_care", ""),
                    "lay_method": m.get("lay_method", ""),
                    "heat_chapters": m.get("heat_chapters", []),
                    "reveal_method": m.get("reveal_chapter", ""),
                    "emotional_payoff": m.get("emotional_payoff", ""),
                    "is_core_mystery": True,
                    "heat_log": [],
                },
            )
            svc.db.add(fs)
        except Exception:
            logger.exception("核心谜题写 Foreshadow 表失败（name=%s）", name)

    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "core_mysteries": mysteries}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        logger.exception("core_mysteries 写 extra 失败")
        svc.db.rollback()


def _persist_opening_contract(svc: Any, project: Project, contract: dict) -> None:
    """写 Project.extra['opening_contract']。"""
    try:
        base = project.extra if isinstance(project.extra, dict) else {}
        project.extra = {**base, "opening_contract": contract}
        flag_modified(project, "extra")
        svc.db.commit()
    except Exception:
        logger.exception("opening_contract 写 extra 失败")
        svc.db.rollback()


def _build_promise_entries(contract: dict) -> list[dict]:
    """从 opening_contract 提取 ReaderPromise 种子条目。"""
    entries: list[dict] = []
    hook = contract.get("chapter1_end_hook") or ""
    if hook:
        entries.append({
            "text": hook,
            "promise_type": "chapter_ending",
            "source_chapter_number": 1,
            "expected_chapter_window": 2,
            "priority": 5,
            "audience_aware": 4,
            "contract_key": "chapter1_end_hook",
        })
    mystery_hook = contract.get("first_mystery_hook") or ""
    if mystery_hook:
        entries.append({
            "text": mystery_hook,
            "promise_type": "name_implication",
            "source_chapter_number": 1,
            "expected_chapter_window": 10,
            "priority": 4,
            "audience_aware": 3,
            "contract_key": "first_mystery_hook",
        })
    for item in (contract.get("chapter_end_promises") or []):
        if not isinstance(item, dict):
            continue
        text = (item.get("promise") or "").strip()
        if text:
            entries.append({
                "text": text,
                "promise_type": item.get("promise_type", "chapter_ending"),
                "source_chapter_number": item.get("chapter"),
                "expected_chapter_window": 3,
                "priority": 3,
                "audience_aware": 3,
                "contract_key": f"ch{item.get('chapter', '')}_promise",
            })
    return entries
