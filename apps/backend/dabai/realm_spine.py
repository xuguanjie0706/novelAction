"""境界脊柱：金手指快升级节奏、章纲升档下限、战力天花板 prompt 与 linter。

与 steps._enforce_realm 配合：模型常把整卷 realm_rank 压在起步档直到卷末，
本模块按卷区间 + 金手指升级机制推算「最低升档节奏」，写库前强制抬升。
"""

from __future__ import annotations

import re

# 金手指机制含以下词 → 开局卷升档宜靠前（约卷长 50% 内触顶）
_FAST_UPGRADE_KEYS = (
    "灌顶", "典当", "直接突破", "瞬间突破", "点数", "满即突破",
    "噬力值", "经验值满", "一键升级", "强行收债",
)

# yinbao 碾压表述 + 高境界名 → 战力通胀
_DOMINANCE_MARKERS = ("碾压", "不堪一击", "不放在眼里", "震慑全场", "无视境界", "稳压", "随手灭")

_SUB_RANK_RE = re.compile(
    r"(?:炼气|筑基|金丹|元婴|化神|炼虚|合体|大乘|淬体|气海|灵纹|神宫)"
    r"(?:境)?([一二三四五六七八九十\d]+)重",
)


def _s(val: object, n: int = 60) -> str:
    return str(val or "").strip()[:n]


def is_fast_upgrade_gf(ctx: dict) -> bool:
    """金手指是否「灌顶/典当/量化直破」类快升级。"""
    gf = ctx.get("golden_finger") or {}
    blob = (gf.get("upgrade_mechanism") or "") + (gf.get("core_ability") or "")
    return any(k in blob for k in _FAST_UPGRADE_KEYS)


def realm_pace_fraction(ctx: dict) -> float:
    """本卷内开始向 realm_end 爬升的进度比例（0~1）。"""
    return 0.50 if is_fast_upgrade_gf(ctx) else 0.72


def min_rank_at_volume_chapter(
    ch_in_vol: int,
    vol_chapters: int,
    start_rank: int,
    end_rank: int,
    *,
    pace_frac: float,
) -> int:
    """卷内第 ch_in_vol 章的 realm_rank 下限（保证卷末触顶）。"""
    span = end_rank - start_rank
    if span <= 0 or vol_chapters <= 1:
        return start_rank
    upgrade_start = max(2, int(vol_chapters * pace_frac))
    if ch_in_vol < upgrade_start:
        return start_rank
    tail = vol_chapters - upgrade_start + 1
    pos = ch_in_vol - upgrade_start + 1
    step = min(span, max(1, int((pos / tail) * span + 0.5)))
    return min(end_rank, start_rank + step)


def enforce_realm_batch(
    batch: list[dict],
    running: int,
    *,
    vr_lo: int | None,
    vr_hi: int | None,
    rmax: int | None,
    vol_planned: int,
    vol_ch_start: int,
    ctx: dict,
) -> int:
    """写库前境界脊柱：单调不减 + 不超卷末/体系上限 + 卷内升档节奏下限。"""
    caps = [x for x in (vr_hi, rmax) if x]
    cap = min(caps) if caps else 10 ** 9
    lo = int(vr_lo or 1)
    hi = min(cap, int(vr_hi or cap))
    pace = realm_pace_fraction(ctx)
    for i, ch in enumerate(batch):
        ch_in_vol = vol_ch_start + i
        min_rr = min_rank_at_volume_chapter(
            ch_in_vol, vol_planned, lo, hi, pace_frac=pace,
        )
        rr = ch.get("realm_rank")
        rr = rr if isinstance(rr, int) else running
        rr = max(rr, running, min_rr)
        rr = min(rr, cap)
        ch["realm_rank"] = rr
        running = rr
    return running


def realm_level_names(ctx: dict) -> dict[int, str]:
    """rank → 境界名。"""
    levels = (ctx.get("power_ladder") or {}).get("levels") or []
    out: dict[int, str] = {}
    for lv in levels:
        if not isinstance(lv, dict):
            continue
        r = lv.get("rank")
        if isinstance(r, int) and lv.get("name"):
            out[r] = str(lv["name"])
    return out


def _realm_name_stems(name: str) -> tuple[str, ...]:
    """境界名在正文中的可匹配词干（含去「境」后缀）。"""
    n = name.strip()
    if not n:
        return ()
    stems = [n]
    if n.endswith("境"):
        stems.append(n[:-1])
    return tuple(dict.fromkeys(stems))


def realm_pace_schedule_note(vol: dict, vol_planned: int, ctx: dict) -> str:
    """注入章纲/节拍：升档应落在哪一段。"""
    lo = vol.get("realm_start_rank") or 1
    hi = vol.get("realm_end_rank") or lo
    if hi <= lo:
        return ""
    pace = realm_pace_fraction(ctx)
    up_ch = max(2, int(vol_planned * pace))
    fast = is_fast_upgrade_gf(ctx)
    return (
        f"  ★升档节奏★：本卷第 {up_ch} 章前后须开始向 rank {hi} 爬升，"
        f"卷末章 realm_rank 必须 = {hi}；"
        f"{'金手指为灌顶/典当式，禁止拖到卷末最后 3 章才破境；' if fast else ''}"
        "realm_rank 升档章的 yinbao 须写清突破，并与 realm_milestones 解锁能力对齐。\n"
    )


def power_ceiling_prompt_block(ctx: dict) -> str:
    """章纲五拍战力天花板（防叙事通胀）。"""
    names = realm_level_names(ctx)
    rank_line = "、".join(f"{r}={n}" for r, n in sorted(names.items())[:10])
    return (
        "\n【战力天花板（硬约束，违反即废稿）】\n"
        "  realm_rank = 本章结束时主角大境界档（上表数字）；"
        "realm_sub_rank = 同境内小层 1～9（仅 realm_rank 未变时可涨，升档时重置为 1）。\n"
        f"  境界对照：{rank_line or '见境界体系档位'}\n"
        "  yinbao/shuang_payoff 禁止写主角稳压、碾压高于「本章 rank+1」大境的敌人；"
        "越一级险胜/借金手指规则反杀可以，跨两级碾压不行。\n"
        "  禁止在 realm_rank 未达某境时写该境威能已常态可用（如 rank=1 炼气时写震慑元婴长老）。\n"
        "  同境内战力起伏用 realm_sub_rank 或金手指规则解释，勿用大境名词凑爽感。\n"
    )


def volume_realm_pace_prompt_addendum(ctx: dict, vol_chapters: int) -> str:
    """卷骨架步：快升级金手指与境界区间绑定。"""
    if not is_fast_upgrade_gf(ctx):
        return (
            "\n★开局卷境界升幅★：realm_end_rank - realm_start_rank 通常 1～2 档；"
            "主角升档宜落在卷后 30% 章节，勿一卷暴涨多档。\n"
        )
    up_ch = max(2, int(vol_chapters * realm_pace_fraction(ctx)))
    return (
        f"\n★金手指快升级（灌顶/典当/量化破境）★：第1卷 realm 升幅仍限 1～2 档，"
        f"但章纲规划须让主角在约第 {up_ch} 章达到 realm_end_rank，"
        "与 golden_finger.first_10_shuang 前几条升级/打脸爽点同章兑现，禁止拖延到卷末。\n"
    )


def _chapter_power_blob(ch: dict) -> str:
    return " ".join(str(ch.get(k) or "") for k in (
        "title", "yinbao", "shuang_payoff", "emotion_turn", "yaqu_setup",
    ))


def lint_power_vs_rank(chapters: list[dict], ctx: dict, add) -> None:
    """REALM-05：叙事战力超过本章 realm_rank 允许范围。"""
    from dabai.linter import Issue

    names = realm_level_names(ctx)
    if not names:
        return
    for ch in chapters:
        num = ch.get("chapter_number")
        rr = ch.get("realm_rank")
        if not isinstance(rr, int):
            continue
        blob = _chapter_power_blob(ch)
        if not any(m in blob for m in _DOMINANCE_MARKERS):
            continue
        for rank, name in names.items():
            if rank <= rr + 1:
                continue
            if not any(s in blob for s in _realm_name_stems(name)):
                continue
            add(Issue(
                "REALM-05", "high", num,
                f"战力通胀：第{num}章 realm_rank={rr}（{names.get(rr, '?')}），"
                f"叙事却碾压/震慑更高境『{name}』（档{rank}）",
                "降 yinbao 对手档位或提前本章 realm_rank；越级须写清规则/代价",
            ))
            break


def lint_sub_rank(chapters: list[dict], add) -> None:
    """REALM-06：realm_sub_rank 在同境内须单调不减。"""
    from dabai.linter import Issue

    prev_rr: int | None = None
    prev_sub: int | None = None
    for ch in chapters:
        num = ch.get("chapter_number")
        rr = ch.get("realm_rank")
        sub = ch.get("realm_sub_rank")
        if not isinstance(rr, int) or not isinstance(sub, int):
            prev_rr = rr if isinstance(rr, int) else prev_rr
            if isinstance(rr, int):
                prev_sub = sub if isinstance(sub, int) else None
            continue
        if prev_rr == rr and prev_sub is not None and sub < prev_sub:
            add(Issue(
                "REALM-06", "medium", num,
                f"realm_sub_rank 回退：{prev_sub}→{sub}（同境 rank={rr}）",
                "同境内小层只涨不降，升大境时 sub 重置为 1",
            ))
        prev_rr, prev_sub = rr, sub
