"""番茄·玄幻修仙直白线：境界预算契约（Realm Budget Contract）。

设计主张（为什么新增本模块，而不是改通用/番茄线）
--------------------------------------------------
通用线把「主角每卷该到第几境」当作 prompt **软约束**（``build_protagonist_progression_prompt_block``
用线性插值塞进提示词，LLM 可以无视），卷级 linter 发现战力问题只 ``warning`` 不阻断
（``steps/volumes.py`` 注释明写「不自动重试 LLM」）。两者叠加，于是反复出现
**「第一卷就把境界修满」**。

本模块把境界进度从「软提示」升级为「**代码确定的硬契约**」，三点关键差异：

1. **前重后轻曲线（front-loaded）**：早卷慢爬（新手村感强、爽点密），高境留给后三分之一。
   通用线的线性插值在「大境多 / 卷数少」时，单卷跨幅天然偏大，再被 LLM 往上抬就崩；
   本模块用凸曲线 + 开局卷硬上限（vol1 至多升 1 大境），从源头压住早期飙升。
2. **窗口落库为单一事实源**：每卷的 ``realm_start_rank / realm_end_rank / boss_realm_rank_cap``
   由代码算定，落 ``Project.extra.cultivation_contract``，下游只读不算。
3. **确定性 clamp**：卷生成后，主角境界字段由契约**覆写**（不信任 LLM 的数字）。
   这让「第一卷修满」在结构上不可能发生——该字段根本不由模型决定。

本模块为**纯函数**（不 import app / ORM / LLM），可独立单测。
红线：本文件 ≤ 600 行。
"""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = "1.0"

# 开局卷（第 1 卷）境界涨幅硬上限：最多 1 个大境，保「新手村」体感。
_VOL1_MAX_GAIN = 1
# 前重后轻曲线指数（>1 即早慢晚快）。1.7 经验值：9 卷 12 境时 vol1 落在 +1。
_FRONT_LOAD_GAMMA = 1.7
# 单卷 BOSS 大境 rank 相对主角卷末的领先上限（越级打脸的合理天花板）。
_BOSS_LEAD_OVER_PROTAGONIST = 2


# ──────────────────────────────────────────────────────
# rank ↔ 境界名
# ──────────────────────────────────────────────────────

def name_at_rank(rank: int, level_names: list[str]) -> str:
    """1-based rank → 大境名；越界则夹到首/尾。"""
    if not level_names:
        return ""
    if rank <= 1:
        return level_names[0]
    if rank >= len(level_names):
        return level_names[-1]
    return level_names[rank - 1]


def clamp_rank(rank: int, lo: int, hi: int) -> int:
    return max(lo, min(int(rank), hi))


# ──────────────────────────────────────────────────────
# 前重后轻进度曲线
# ──────────────────────────────────────────────────────

def front_loaded_end_ranks(
    start_rank: int,
    end_rank: int,
    n_volumes: int,
    *,
    gamma: float = _FRONT_LOAD_GAMMA,
    vol1_max_gain: int = _VOL1_MAX_GAIN,
) -> list[int]:
    """计算各卷**卷末**主角应达到的 1-based rank（前重后轻）。

    保证（这些是契约对调用方的承诺，单测覆盖）：
      - 长度 == n_volumes；
      - 严格非递减（不会倒退）；
      - 末卷 == end_rank（终局必达顶点，不烂尾在中段）；
      - 第 1 卷涨幅 ≤ vol1_max_gain（开局慢爬，杜绝「第一卷修满」）；
      - 整体凸形（早期增量 ≤ 后期增量），即高境集中在后段。

    Args:
        start_rank: 主角全书起点 rank（含，1-based）。
        end_rank:   主角全书终点 rank（含）。
        n_volumes:  卷数（>0）。
        gamma:      曲线指数，>1 越大越前重后轻。
        vol1_max_gain: 第 1 卷相对起点的最大大境涨幅。

    Returns:
        各卷卷末 rank 列表（长度 n_volumes）。
    """
    if n_volumes <= 0:
        return []
    start_rank = int(start_rank)
    end_rank = int(end_rank)
    if n_volumes == 1:
        return [max(end_rank, start_rank)]
    span = end_rank - start_rank
    if span <= 0:
        # 起点 ≥ 终点（异常输入）：全程停在终点，避免倒退。
        return [end_rank] * n_volumes

    ranks: list[int] = []
    for i in range(1, n_volumes + 1):
        cum_frac = (i / n_volumes) ** gamma  # 凸：早期 cum_frac 偏小
        ranks.append(start_rank + round(cum_frac * span))

    # 开局卷硬上限：第 1 卷至多升 vol1_max_gain 个大境。
    ranks[0] = min(ranks[0], start_rank + max(0, vol1_max_gain))
    ranks[0] = max(ranks[0], start_rank)

    # 强制非递减。
    for i in range(1, n_volumes):
        if ranks[i] < ranks[i - 1]:
            ranks[i] = ranks[i - 1]

    # 夹到天花板并钉死末卷 == 终点。
    ranks = [clamp_rank(r, start_rank, end_rank) for r in ranks]
    ranks[-1] = end_rank

    # 末卷被钉高后回扫一遍，保证仍非递减（不会出现 [..,5,4] 之类）。
    for i in range(n_volumes - 2, -1, -1):
        if ranks[i] > ranks[i + 1]:
            ranks[i] = ranks[i + 1]
    # 再次保证开局卷未被回扫破坏其上限语义（回扫只会调小，安全）。
    return ranks


def boss_cap_at(vol_end_rank: int, max_rank: int, *, lead: int = _BOSS_LEAD_OVER_PROTAGONIST) -> int:
    """单卷 BOSS 大境 rank 上限：主角卷末 + 领先值，但不超过全书顶点。"""
    return clamp_rank(vol_end_rank + max(0, lead), 1, max_rank)


# ──────────────────────────────────────────────────────
# 契约装配
# ──────────────────────────────────────────────────────

def build_cultivation_contract(
    level_names: list[str],
    start_rank: int,
    end_rank: int,
    n_volumes: int,
    *,
    realm_axis_name: str = "",
) -> dict:
    """装配境界预算契约（单一事实源）。

    Returns:
        {
          "version", "realm_axis_name", "level_names",
          "start_rank", "end_rank", "n_volumes",
          "volumes": [ {index, realm_start_rank, realm_end_rank,
                        realm_start, realm_end,
                        boss_realm_rank_cap, boss_realm_cap_name}, ... ]
        }
    """
    max_rank = len(level_names) if level_names else max(end_rank, 1)
    start_rank = clamp_rank(start_rank, 1, max_rank)
    end_rank = clamp_rank(end_rank, 1, max_rank)
    if end_rank < start_rank:
        end_rank = start_rank

    end_ranks = front_loaded_end_ranks(start_rank, end_rank, n_volumes)
    volumes: list[dict] = []
    for i, er in enumerate(end_ranks):
        sr = start_rank if i == 0 else end_ranks[i - 1]
        boss_cap = boss_cap_at(er, max_rank)
        volumes.append({
            "index": i,
            "realm_start_rank": sr,
            "realm_end_rank": er,
            "realm_start": name_at_rank(sr, level_names),
            "realm_end": name_at_rank(er, level_names),
            "boss_realm_rank_cap": boss_cap,
            "boss_realm_cap_name": name_at_rank(boss_cap, level_names),
        })
    return {
        "version": CONTRACT_VERSION,
        "realm_axis_name": realm_axis_name,
        "level_names": list(level_names),
        "start_rank": start_rank,
        "end_rank": end_rank,
        "n_volumes": n_volumes,
        "volumes": volumes,
    }


def contract_from_ctx(ctx: dict, n_volumes: int) -> dict | None:
    """从 Bootstrap ctx（须已 ``hydrate_fanqie_power_ctx``）装配契约。

    读取 ``power_level_names`` 与 ``power_systems_full[0]`` 的主角起止 rank；
    缺失时退化为「起点 1 → 终点 末档」。无境界名则返回 None（无法约束）。
    """
    level_names = list(ctx.get("power_level_names") or [])
    if not level_names:
        return None
    max_rank = len(level_names)
    start_rank, end_rank = 1, max_rank
    for snap in ctx.get("power_systems_full") or []:
        if (snap.get("axis_role") or "primary") == "primary":
            sr = snap.get("protagonist_current_rank")
            er = snap.get("protagonist_end_rank")
            if isinstance(sr, int) and sr > 0:
                start_rank = sr
            if isinstance(er, int) and er > 0:
                end_rank = er
            break
    ladder = ctx.get("power_ladder") if isinstance(ctx.get("power_ladder"), dict) else {}
    realm_axis_name = str((ladder or {}).get("realm_axis_name") or "").strip()
    return build_cultivation_contract(
        level_names, start_rank, end_rank, n_volumes, realm_axis_name=realm_axis_name,
    )


# ──────────────────────────────────────────────────────
# Prompt 硬约束块
# ──────────────────────────────────────────────────────

def build_cultivation_budget_block(contract: dict | None) -> str:
    """卷生成 prompt 的境界预算硬约束块（每卷窗口由代码给定，模型只在窗口内写剧情）。"""
    if not contract or not contract.get("volumes"):
        return ""
    level_names = contract.get("level_names") or []
    ladder_line = " → ".join(level_names)
    lines: list[str] = [
        "\n【⚠️ 境界预算契约（硬约束，逐卷已锁定，不得自行抬高）】",
        f"全书唯一合法大境（低→高）：{ladder_line}",
        (
            f"主角全书：{name_at_rank(contract['start_rank'], level_names)}"
            f"（rank {contract['start_rank']}）→ "
            f"{name_at_rank(contract['end_rank'], level_names)}（rank {contract['end_rank']}）"
        ),
        "下列每卷的【主角卷初→卷末境界】【BOSS 境界上限】已由系统锁定，"
        "你只能在该窗口内安排剧情，protagonist_realm_start/end 必须照抄，禁止跨窗：",
    ]
    for v in contract["volumes"]:
        lines.append(
            f"  第{v['index'] + 1}卷：主角 {v['realm_start']} → {v['realm_end']}"
            f"（rank {v['realm_start_rank']}→{v['realm_end_rank']}）"
            f"｜BOSS 大境 rank ≤ {v['boss_realm_cap_name']}（{v['boss_realm_rank_cap']}）"
        )
    lines.append(
        "铁律：① 第一卷只能在开局两三档境界内，禁止速通到高境；"
        "② 大境不可跳级，破境须连续并交代异象/代价；"
        "③ 仅末卷可达全书终点境界；"
        "④ summary/conflict 中提到的境界须与本卷窗口一致。"
    )
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────
# 确定性 clamp（卷生成后执行——核心强制点）
# ──────────────────────────────────────────────────────

def clamp_volume_extra_to_contract(
    vol_extra: dict,
    vol_index: int,
    contract: dict,
) -> list[str]:
    """用契约**覆写**单卷 extra 的主角境界字段（就地修改）。

    这是「第一卷修满」无法发生的根本保证：境界数字来自代码契约，不来自 LLM。
    主角字段直接覆写；BOSS 仅在超过 rank 上限时下调到上限名（保留 LLM 命名风格）。

    Returns:
        本卷被纠正项的中文说明列表（用于日志/审计）。
    """
    vols = contract.get("volumes") or []
    if vol_index >= len(vols):
        return []
    spec = vols[vol_index]
    notes: list[str] = []

    old_start = (vol_extra.get("protagonist_realm_start") or "").strip()
    old_end = (vol_extra.get("protagonist_realm_end") or "").strip()
    if old_start != spec["realm_start"]:
        notes.append(f"主角卷初 {old_start or '空'} → 契约 {spec['realm_start']}")
    if old_end != spec["realm_end"]:
        notes.append(f"主角卷末 {old_end or '空'} → 契约 {spec['realm_end']}")

    vol_extra["protagonist_realm_start"] = spec["realm_start"]
    vol_extra["protagonist_realm_end"] = spec["realm_end"]
    vol_extra["protagonist_realm_start_rank"] = spec["realm_start_rank"]
    vol_extra["protagonist_realm_end_rank"] = spec["realm_end_rank"]
    vol_extra["boss_realm_rank_cap"] = spec["boss_realm_rank_cap"]
    vol_extra["cultivation_contract_bound"] = True
    return notes


def boss_name_within_cap(
    boss_realm_name: str,
    vol_index: int,
    contract: dict,
    name_to_rank: dict[str, int],
) -> tuple[str, str | None]:
    """若 BOSS 大境 rank 超过本卷上限，下调到上限大境名。

    Args:
        boss_realm_name: LLM 给的 BOSS 境界文本（可能带小境）。
        name_to_rank:    大境名 → rank（1-based）。

    Returns:
        (规范后的 BOSS 境界名, 纠正说明或 None)。无法解析时原样返回。
    """
    vols = contract.get("volumes") or []
    if vol_index >= len(vols):
        return boss_realm_name, None
    cap_rank = vols[vol_index]["boss_realm_rank_cap"]
    s = (boss_realm_name or "").strip()
    if not s or not name_to_rank:
        return s, None
    # 解析 BOSS 所属大境 rank（最长匹配大境名）。
    boss_rank = name_to_rank.get(s)
    if boss_rank is None:
        for name in sorted(name_to_rank, key=len, reverse=True):
            if name and name in s:
                boss_rank = name_to_rank[name]
                break
    if boss_rank is None or boss_rank <= cap_rank:
        return s, None
    cap_name = vols[vol_index]["boss_realm_cap_name"]
    return cap_name, f"BOSS 境界「{s}」(rank {boss_rank}) 超第{vol_index + 1}卷上限，下调为「{cap_name}」"


# ──────────────────────────────────────────────────────
# 校验（落库后断言；契约 clamp 后理应零问题，用于兜底捕获装配 bug）
# ──────────────────────────────────────────────────────

def validate_volumes_against_contract(
    vol_extras: list[dict],
    contract: dict,
) -> list[str]:
    """核对落库卷 extra 与契约是否一致；返回问题列表（空 == 通过）。"""
    issues: list[str] = []
    vols = contract.get("volumes") or []
    if len(vol_extras) != len(vols):
        issues.append(f"卷数不符：实际 {len(vol_extras)}，契约 {len(vols)}")
    prev_end = contract.get("start_rank", 1)
    for i, spec in enumerate(vols):
        if i >= len(vol_extras):
            break
        ex = vol_extras[i] or {}
        er = ex.get("protagonist_realm_end_rank")
        if er != spec["realm_end_rank"]:
            issues.append(
                f"第{i + 1}卷主角卷末 rank={er} 与契约 {spec['realm_end_rank']} 不符"
            )
        if isinstance(er, int) and er < prev_end:
            issues.append(f"第{i + 1}卷主角境界倒退（{prev_end}→{er}）")
        if isinstance(er, int):
            prev_end = er
    if vols:
        last = vol_extras[-1] if vol_extras else {}
        if last.get("protagonist_realm_end_rank") != contract["end_rank"]:
            issues.append("末卷主角境界未达全书终点")
    return issues
