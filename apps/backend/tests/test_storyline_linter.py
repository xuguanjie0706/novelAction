"""storyline_linter 单元测试（SL-01～SL-09）。"""

from app.services.bootstrap.storyline_linter import (
    has_blocking_issues,
    lint_storyline_weave,
    normalize_storyline_weights,
)


def _identity():
    return [
        {
            "name": "主线：逆天",
            "line_type": "main",
            "weight": 0.4,
            "theme_link": "弱者逆袭",
            "resolution_volume_hint": 4,
        },
        {
            "name": "感情线：羁绊",
            "line_type": "romance",
            "weight": 0.3,
            "theme_link": "关系中的力量",
            "resolution_volume_hint": 3,
        },
        {
            "name": "势力线：争霸",
            "line_type": "faction",
            "weight": 0.3,
            "theme_link": "阶层壁垒",
            "resolution_volume_hint": 2,
        },
    ]


def _weave_ok(n: int = 3, phases: list[str] | None = None):
    phases = phases or (["opening", "climax", "ending"][:n] + ["rising"] * max(0, n - 3))[:n]
    matrix = {}
    names = ["主线：逆天", "感情线：羁绊", "势力线：争霸"]
    for name in names:
        rows = []
        for i in range(n):
            if name.startswith("主线"):
                tension = 100 if phases[i] == "climax" else 25 + i * 10
            else:
                tension = min(60, 30 + i * 10)
            rows.append({
                "vol_index": i,
                "beat": f"{name}第{i}卷",
                "tension": tension,
                "is_active": True,
                "chapter_hint_start": 2,
                "chapter_hint_peak": 15,
            })
        matrix[name] = rows
    crossovers = [
        {
            "line_a": "主线：逆天",
            "line_b": "感情线：羁绊",
            "at_vol": i,
            "trigger": "保护暴露实力",
            "effect_on_both": "感情加深；引来新敌",
        }
        for i in range(n)
    ]
    return {"weave_matrix": matrix, "crossover_nodes": crossovers}


def test_normalize_weights():
    lines = [{"weight": 0.2}, {"weight": 0.2}]
    out = normalize_storyline_weights(lines)
    assert abs(sum(x["weight"] for x in out) - 1.0) < 0.001


def test_sl01_main_weight_block():
    identity = _identity()
    identity[0]["weight"] = 0.1
    issues = lint_storyline_weave(identity, _weave_ok(), 3, ["opening", "climax", "ending"])
    assert any(i.rule_id == "SL-01" for i in issues)


def test_sl03_two_active_per_volume():
    weave = _weave_ok(2)
    for beats in weave["weave_matrix"].values():
        beats[0]["is_active"] = False
        beats[1]["is_active"] = False
    issues = lint_storyline_weave(_identity(), weave, 2, ["opening", "ending"])
    assert any(i.rule_id == "SL-03" for i in issues)
    assert has_blocking_issues(issues)


def test_valid_weave_no_block():
    phases = ["opening", "climax", "ending"]
    issues = lint_storyline_weave(_identity(), _weave_ok(3), 3, phases)
    blocks = [i for i in issues if i.severity == "BLOCK"]
    assert not blocks
