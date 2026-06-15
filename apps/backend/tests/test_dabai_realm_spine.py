"""境界脊柱：升档节奏与战力通胀 linter。"""
from dabai.config import DabaiConfig
from dabai.linter import lint_chapters
from dabai.realm_spine import (
    enforce_realm_batch,
    is_fast_upgrade_gf,
    min_rank_at_volume_chapter,
)


def test_fast_upgrade_gf_detects_dian_dang():
    ctx = {"golden_finger": {"upgrade_mechanism": "典当物换黄泉点数灌顶破境"}}
    assert is_fast_upgrade_gf(ctx)


def test_enforce_realm_batch_lifts_stuck_floor():
    """模型全回 rank=1 时，卷末仍须触顶 realm_end=2。"""
    ctx = {"golden_finger": {"upgrade_mechanism": "灌顶提升境界"}}
    batch = [{"chapter_number": i, "realm_rank": 1} for i in range(1, 31)]
    end = enforce_realm_batch(
        batch, 1,
        vr_lo=1, vr_hi=2, rmax=8,
        vol_planned=30, vol_ch_start=1, ctx=ctx,
    )
    assert end == 2
    assert batch[-1]["realm_rank"] == 2
    assert batch[12]["realm_rank"] == 1  # 第13章仍应在炼气档
    assert batch[20]["realm_rank"] >= 1


def test_min_rank_fast_pace_reaches_end_before_last_chapter():
    pace = 0.5
    assert min_rank_at_volume_chapter(30, 30, 1, 2, pace_frac=pace) == 2
    assert min_rank_at_volume_chapter(10, 30, 1, 2, pace_frac=pace) == 1


def test_realm_05_power_inflation():
    cfg = DabaiConfig()
    ctx = {
        "power_ladder": {
            "levels": [
                {"rank": 1, "name": "炼气境"},
                {"rank": 2, "name": "筑基境"},
                {"rank": 4, "name": "元婴境"},
            ],
        },
    }
    ch = {
        "chapter_number": 20,
        "realm_rank": 1,
        "shuang_type": "打脸",
        "yaqu_setup": "被压",
        "emotion_turn": "从隐忍→触发→出手",
        "yinbao": "震慑元婴长老，对方不堪一击",
        "shuang_payoff": "当着全场的面碾压元婴长老",
        "witnesses": ["路人"],
        "end_hook": "更强敌人",
        "new_info_count": 1,
    }
    report = lint_chapters([ch], cfg, realm_max=4, realm_range=(1, 2), ctx=ctx)
    assert any(i.rule_id == "REALM-05" for i in report.issues)
