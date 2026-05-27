"""故事线织网 Linter（SL-01～SL-09）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StorylineLintIssue:
    rule_id: str
    severity: str  # BLOCK | WARN
    message: str


def normalize_storyline_weights(identity_lines: list[dict]) -> list[dict]:
    """SL-02：将 weight 归一化到总和 1.0。"""
    total = sum(float(x.get("weight") or 0) for x in identity_lines)
    if total <= 0:
        return identity_lines
    out = []
    for item in identity_lines:
        copy = dict(item)
        w = float(copy.get("weight") or 0) / total
        copy["weight"] = round(w, 4)
        out.append(copy)
    return out


def _main_line(identity_lines: list[dict]) -> dict | None:
    for line in identity_lines:
        if line.get("line_type") == "main":
            return line
    return identity_lines[0] if identity_lines else None


def _beats_by_vol(matrix: dict[str, list[dict]], n_volumes: int) -> dict[int, list[tuple[str, dict]]]:
    """vol_index -> [(line_name, beat_dict), ...]"""
    per_vol: dict[int, list[tuple[str, dict]]] = {i: [] for i in range(n_volumes)}
    for name, beats in (matrix or {}).items():
        for b in beats or []:
            if not isinstance(b, dict):
                continue
            vi = int(b.get("vol_index", -1))
            if 0 <= vi < n_volumes:
                per_vol[vi].append((name, b))
    return per_vol


def lint_storyline_weave(
    identity_lines: list[dict],
    weave_payload: dict[str, Any],
    n_volumes: int,
    volume_phases: list[str] | None = None,
) -> list[StorylineLintIssue]:
    """校验身份 + 织网矩阵；返回 BLOCK/WARN 问题列表。"""
    issues: list[StorylineLintIssue] = []
    if not identity_lines:
        issues.append(StorylineLintIssue("SL-00", "BLOCK", "故事线身份为空"))
        return issues

    main = _main_line(identity_lines)
    main_name = (main or {}).get("name", "")

    # SL-01
    main_w = float((main or {}).get("weight") or 0)
    if main_w < 0.30:
        issues.append(StorylineLintIssue(
            "SL-01", "BLOCK", f"主线 weight={main_w:.2f} < 0.30",
        ))

    # SL-02
    w_sum = sum(float(x.get("weight") or 0) for x in identity_lines)
    if not (0.95 <= w_sum <= 1.05):
        issues.append(StorylineLintIssue(
            "SL-02", "BLOCK", f"weight 之和={w_sum:.3f}，不在 [0.95, 1.05]",
        ))

    matrix = weave_payload.get("weave_matrix") if isinstance(weave_payload, dict) else {}
    crossovers = weave_payload.get("crossover_nodes") if isinstance(weave_payload, dict) else []
    per_vol = _beats_by_vol(matrix, n_volumes)
    phases = volume_phases or ["rising"] * n_volumes

    # SL-03
    for vi in range(n_volumes):
        active = [n for n, b in per_vol[vi] if b.get("is_active", True)]
        if len(active) < 2:
            issues.append(StorylineLintIssue(
                "SL-03", "BLOCK", f"第{vi}卷仅 {len(active)} 条线激活（需≥2）",
            ))

    # SL-04：连续休眠卷
    line_names = [x.get("name") for x in identity_lines if x.get("name")]
    for name in line_names:
        dormant_run = 0
        for vi in range(n_volumes):
            beats = [b for n, b in per_vol[vi] if n == name]
            active = beats[0].get("is_active", True) if beats else False
            if not active:
                dormant_run += 1
                if dormant_run > 2:
                    issues.append(StorylineLintIssue(
                        "SL-04", "BLOCK", f"「{name}」连续休眠超过 2 卷（至 vol {vi}）",
                    ))
                    break
            else:
                dormant_run = 0

    # SL-05
    cross_by_vol: dict[int, int] = {}
    for c in crossovers or []:
        if isinstance(c, dict):
            av = int(c.get("at_vol", -1))
            if 0 <= av < n_volumes:
                cross_by_vol[av] = cross_by_vol.get(av, 0) + 1
    for vi in range(n_volumes):
        if cross_by_vol.get(vi, 0) < 1:
            issues.append(StorylineLintIssue(
                "SL-05", "WARN", f"第{vi}卷无 crossover_node",
            ))

    # SL-06
    for vi in range(n_volumes):
        peaks = sum(1 for _, b in per_vol[vi] if int(b.get("tension") or 0) >= 75)
        if peaks > 2:
            issues.append(StorylineLintIssue(
                "SL-06", "WARN", f"第{vi}卷 {peaks} 条线张力峰值≥75（建议≤2）",
            ))

    # SL-07：主线在 climax 卷张力最高
    climax_vols = [i for i, p in enumerate(phases) if p == "climax"]
    if main_name and climax_vols and matrix:
        main_beats = matrix.get(main_name) or []
        all_tensions: list[tuple[int, int]] = []
        for name, beats in (matrix or {}).items():
            for b in beats or []:
                if isinstance(b, dict):
                    all_tensions.append((int(b.get("vol_index", -1)), int(b.get("tension") or 0)))
        main_max = max(
            (int(b.get("tension") or 0) for b in main_beats if isinstance(b, dict)),
            default=0,
        )
        global_max = max((t for _, t in all_tensions), default=0)
        climax_main = max(
            (int(b.get("tension") or 0) for b in main_beats
             if isinstance(b, dict) and int(b.get("vol_index", -1)) in climax_vols),
            default=0,
        )
        if global_max > 0 and climax_main < global_max:
            issues.append(StorylineLintIssue(
                "SL-07", "BLOCK",
                f"主线在 climax 卷最高张力 {climax_main} < 全书最高 {global_max}",
            ))

    # SL-08：收束卷顺序
    hints = [
        (x.get("name"), int(x.get("resolution_volume_hint", 999)))
        for x in identity_lines
        if x.get("name")
    ]
    main_hint = next((h for n, h in hints if n == main_name), None)
    if main_hint is not None:
        for name, hint in hints:
            if name != main_name and hint > main_hint:
                issues.append(StorylineLintIssue(
                    "SL-08", "WARN",
                    f"「{name}」收束卷 {hint} 晚于主线 {main_hint}",
                ))

    # SL-09
    for line in identity_lines:
        tl = (line.get("theme_link") or "").strip()
        if not tl:
            issues.append(StorylineLintIssue(
                "SL-09", "WARN", f"「{line.get('name')}」theme_link 为空",
            ))

    return issues


def has_blocking_issues(issues: list[StorylineLintIssue]) -> bool:
    return any(i.severity == "BLOCK" for i in issues)
