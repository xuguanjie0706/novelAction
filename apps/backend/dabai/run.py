"""CLI 入口：python -m dabai.run --logline "..."

示例：
  python -m dabai.run --logline "..." --volume-chapters 30 --stop-after chapter_outlines
运行前先 export DABAI_BASE_URL / DABAI_API_KEY / DABAI_MODEL。
"""

from __future__ import annotations

import argparse
import logging
import sys

from dabai import linter
from dabai.config import PIPELINE_STEPS, DabaiConfig
from dabai.linter import lint_chapters
from dabai.llm_client import LLMError
from dabai.pipeline import run_bootstrap


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="dabai.run", description="大白文 bootstrap（爽点节拍器）")
    p.add_argument("--logline", required=True, help="一句话创意")
    p.add_argument("--volume-count", type=int, default=6, help="卷数")
    p.add_argument("--volume-chapters", type=int, default=30, help="每卷章数")
    p.add_argument("--big-beat-every", type=int, default=5, help="每N章一个大爆点")
    p.add_argument("--stop-after", choices=PIPELINE_STEPS, default=None,
                   help="跑到某步即停（含该步）")
    p.add_argument("--quiet", action="store_true", help="只打印结果摘要")
    return p.parse_args(argv)


def _print_summary(result) -> None:
    ctx = result.ctx
    print("\n" + "=" * 60)
    print(f"大白文 bootstrap 完成：{result.cfg.logline}")
    print("=" * 60)
    gf = ctx.get("golden_finger") or {}
    print(f"金手指：{gf.get('name', '—')}（{gf.get('type', '')}）")
    lv = (ctx.get("power_ladder") or {}).get("levels", [])
    print(f"境界：{'→'.join(x.get('name', '') for x in lv)}")
    print(f"势力：{len(ctx.get('factions') or [])}　人物：{len(ctx.get('characters') or [])}　"
          f"故事线：{len(ctx.get('storylines') or [])}　卷：{len(ctx.get('volumes') or [])}")
    chapters = ctx.get("chapter_outlines") or []
    print(f"章纲：{len(chapters)} 章（第1卷）")
    if chapters:
        print("\n爽点节拍序列（前10章）：")
        for ch in chapters[:10]:
            big = "★" if ch.get("is_big_beat") else " "
            print(f"  {big}第{ch['chapter_number']:>2}章 [{ch.get('shuang_type','?'):　<4}] "
                  f"{ch.get('title','')}")
    if result.failed_steps:
        print(f"\n⚠ 失败步骤：{result.failed_steps}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = DabaiConfig(
        logline=args.logline,
        volume_count=args.volume_count,
        volume_chapters=args.volume_chapters,
        big_beat_every=args.big_beat_every,
        stop_after=args.stop_after,
    )
    try:
        result = run_bootstrap(cfg)
    except LLMError as exc:
        print(f"\n✗ 无法启动：{exc}", file=sys.stderr)
        return 2
    _print_summary(result)

    # 重新构造 report 对象以打印详细 linter 文本
    chapters = result.ctx.get("chapter_outlines")
    if chapters:
        print("\n" + linter.format_report(lint_chapters(chapters, cfg)))

    path = result.save()
    print(f"\n产物已写入：{path}")
    # 有 critical 阻断时返回非零码，方便 CI
    rep = result.linter_report
    return 1 if (rep and rep.get("status") == "blocked") else 0


if __name__ == "__main__":
    raise SystemExit(main())
