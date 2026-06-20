"""Cursor Agent 按 dabai 生产 prompt 链路写章：导出提示词 / 回填 Agent 产出。

用法：
  # 导出第 1 章完整 prompt 链（导演单 → 分场 → 正文）
  python scripts/cursor_agent_lab_write.py dump \\
    --project-id bf771cb3-c78d-4801-951e-1cde1c9cf410 --chapter 1

  # 回填 Agent 按提示词生成的 JSON/正文并落库
  python scripts/cursor_agent_lab_write.py apply \\
    --project-id ... --chapter 1 --input /path/to/ch1_agent.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.dabai import DabaiChapterOutline, DabaiProject  # noqa: E402
from app.services.dabai.intensity import resolve_dabai_intensity  # noqa: E402
from app.services.dabai.lab_draft_context import (  # noqa: E402
    build_lab_draft_context_async,
)
from app.services.dabai.lab_ledger import build_ledger_block, seed_ledgers  # noqa: E402
from app.services.dabai.lab_pre_warn import (  # noqa: E402
    PREWARN_VERSION,
    build_lab_prewarn_prompt,
    persist_lab_pre_warn,
)
from app.services.dabai.lab_prompt_shared import build_location_bridge_block  # noqa: E402
from app.services.dabai.lab_scene_plan import (  # noqa: E402
    build_sceneplan_prompt,
    finalize_scene_plan_result,
    format_scene_block,
    persist_scene_plan,
)
from app.services.dabai.lab_word_budget import chapter_word_target  # noqa: E402
from app.services.dabai.prewarn_format import format_prewarn_block  # noqa: E402
from app.services.dabai_write import build_prose_prompt  # noqa: E402


def _load_chapter(db, project_id: UUID, chapter_no: int) -> tuple[DabaiProject, DabaiChapterOutline]:
    project = db.query(DabaiProject).filter(DabaiProject.id == project_id).first()
    if not project:
        raise SystemExit(f"项目不存在: {project_id}")
    ch = (
        db.query(DabaiChapterOutline)
        .filter(
            DabaiChapterOutline.project_id == project_id,
            DabaiChapterOutline.chapter_number == chapter_no,
        )
        .first()
    )
    if not ch:
        raise SystemExit(f"第{chapter_no}章不存在")
    return project, ch


async def _build_chain(db, project: DabaiProject, ch: DabaiChapterOutline) -> dict:
    seed_ledgers(db, project)
    ctx = await build_lab_draft_context_async(db, project, ch)
    ledger_block = build_ledger_block(db, project, ch)
    prev_ch = None
    bridge = ""
    if (ch.chapter_number or 0) > 1:
        prev_ch = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
        if prev_ch:
            bridge = build_location_bridge_block(prev_ch, ch, ctx.prev_tail)

    opening_no_prior = (ch.chapter_number or 1) == 1 and not (
        ctx.prev_full_block or ctx.prev_tail
    ).strip()

    pw_sys, pw_user = build_lab_prewarn_prompt(
        project, ch, ctx, ledger_block,
        bridge_evidence=bridge, opening_no_prior=opening_no_prior,
    )
    target = chapter_word_target(ch)
    return {
        "project_id": str(project.id),
        "chapter_number": ch.chapter_number,
        "chapter_id": str(ch.id),
        "title": project.title,
        "expected_words": target,
        "intensity": resolve_dabai_intensity(project),
        "steps": {
            "pre_warn": {"system": pw_sys, "user": pw_user},
        },
        "context_preview": {
            "prev_tail_len": len(ctx.prev_tail or ""),
            "has_prev_full": bool(ctx.prev_full_block),
            "ledger_len": len(ledger_block),
        },
    }


async def cmd_dump(args: argparse.Namespace) -> None:
    db = SessionLocal()
    project, ch = _load_chapter(db, UUID(args.project_id), args.chapter)
    chain = await _build_chain(db, project, ch)
    out = Path(args.output) if args.output else Path(
        f"/tmp/dabai_agent_ch{args.chapter}_prompts.json"
    )
    out.write_text(json.dumps(chain, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: dumped → {out}")
    print(f"  expected_words={chain['expected_words']}")
    db.close()


async def cmd_expand(args: argparse.Namespace) -> None:
    """已有导演单 JSON 时，导出分场 + 正文 prompt（供 Agent 第二步）。"""
    pre_warn = json.loads(Path(args.prewarn).read_text(encoding="utf-8"))
    db = SessionLocal()
    project, ch = _load_chapter(db, UUID(args.project_id), args.chapter)
    seed_ledgers(db, project)
    ctx = await build_lab_draft_context_async(db, project, ch)
    ledger_block = build_ledger_block(db, project, ch)
    prev_ch = None
    if (ch.chapter_number or 0) > 1:
        prev_ch = (
            db.query(DabaiChapterOutline)
            .filter(
                DabaiChapterOutline.project_id == project.id,
                DabaiChapterOutline.chapter_number == ch.chapter_number - 1,
            )
            .first()
        )
    pre_warn_block = format_prewarn_block(pre_warn)
    sp_sys, sp_user = build_sceneplan_prompt(
        project, ch, ctx,
        pre_warn_block=pre_warn_block,
        ledger_block=ledger_block,
        pre_warn_result=pre_warn,
        prev_ch=prev_ch,
    )
    scene_raw = json.loads(Path(args.scene).read_text(encoding="utf-8")) if args.scene else {}
    scene_plan = finalize_scene_plan_result(scene_raw, ch) if scene_raw else {}
    scene_block = format_scene_block(scene_plan) if scene_plan.get("scenes") else ""
    prose_sys, prose_user = build_prose_prompt(
        project, ch,
        prev_tail=ctx.prev_tail,
        recent_plot_block=ctx.recent_plot_block,
        pre_warn_block=pre_warn_block,
        scene_block=scene_block,
        ledger_block=ledger_block,
        memory_block=ctx.memory_block,
        clue_block=ctx.clue_block,
        panel_block=ctx.panel_block,
        prev_full_block=ctx.prev_full_block,
        prev_hook_block=ctx.prev_hook_block,
        narrative_state_block=ctx.narrative_state_block,
        scene_plan=scene_plan if scene_plan.get("scenes") else None,
        intensity=resolve_dabai_intensity(project),
    )
    out = {
        "chapter_number": ch.chapter_number,
        "expected_words": chapter_word_target(ch),
        "steps": {
            "scene_plan": {"system": sp_sys, "user": sp_user},
            "prose": {"system": prose_sys, "user": prose_user},
        },
    }
    out_path = Path(args.output) if args.output else Path(
        f"/tmp/dabai_agent_ch{args.chapter}_prose_prompts.json"
    )
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: expanded → {out_path}")
    db.close()


async def cmd_apply(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    db = SessionLocal()
    project, ch = _load_chapter(db, UUID(args.project_id), args.chapter)

    pre_warn = payload.get("pre_warn_result")
    scene_raw = payload.get("scene_plan_result")
    prose = (payload.get("prose") or "").strip()
    if not isinstance(pre_warn, dict) or not isinstance(scene_raw, dict) or not prose:
        raise SystemExit("input 须含 pre_warn_result / scene_plan_result / prose")

    pre_warn = dict(pre_warn)
    pre_warn["version"] = PREWARN_VERSION
    scene_plan = finalize_scene_plan_result(scene_raw, ch)
    brief = format_prewarn_block(pre_warn)
    persist_lab_pre_warn(db, project, ch, pre_warn, brief)
    scene_brief = format_scene_block(scene_plan)
    persist_scene_plan(db, project, ch, scene_plan, scene_brief)

    ch.content = prose
    ch.status = "written"
    db.commit()

    wc = len(prose)
    target = chapter_word_target(ch)
    lo = max(1600, target - 200)
    hi = target + 200
    if wc < lo or wc > hi:
        print(f"WARN: 字数 {wc} 不在允许区间 {lo}～{hi}（目标 {target}）")
    print(f"OK: chapter {args.chapter} applied")
    print(f"  words={wc} target={target} delta={wc - target:+d}")
    print(f"  scenes={len(scene_plan.get('scenes') or [])}")
    db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Cursor Agent dabai prompt pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="导出 prompt 链")
    d.add_argument("--project-id", required=True)
    d.add_argument("--chapter", type=int, required=True)
    d.add_argument("--output", default="")

    e = sub.add_parser("expand", help="导出分场/正文 prompt（需先有导演单 JSON）")
    e.add_argument("--project-id", required=True)
    e.add_argument("--chapter", type=int, required=True)
    e.add_argument("--prewarn", required=True, help="导演单 JSON 文件")
    e.add_argument("--scene", default="", help="分场 JSON（可选，用于导出正文 prompt）")
    e.add_argument("--output", default="")

    a = sub.add_parser("apply", help="回填 Agent 产出")
    a.add_argument("--project-id", required=True)
    a.add_argument("--chapter", type=int, required=True)
    a.add_argument("--input", required=True)

    args = p.parse_args()
    if args.cmd == "dump":
        asyncio.run(cmd_dump(args))
    elif args.cmd == "expand":
        asyncio.run(cmd_expand(args))
    elif args.cmd == "apply":
        asyncio.run(cmd_apply(args))


if __name__ == "__main__":
    main()
