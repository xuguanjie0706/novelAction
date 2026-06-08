"""大白文 linter：境界脊柱 REALM 闸门 + DB-09 转折拍。"""
from dabai.config import DabaiConfig
from dabai.linter import lint_chapters


def _ch(num: int, **kw) -> dict:
    base = {
        "chapter_number": num,
        "shuang_type": "打脸",
        "yaqu_setup": "被羞辱",
        "emotion_turn": "从隐忍→听到辱及亡母（触发）→杀意上涌",
        "shuang_payoff": "当众打脸，全场震惊",
        "witnesses": ["路人"],
        "end_hook": "更强敌人现身",
        "new_info_count": 1,
        "is_big_beat": num == 5,
        "realm_rank": 1,
    }
    base.update(kw)
    return base


def test_realm_01_blocks_rank_regression():
    cfg = DabaiConfig()
    chapters = [_ch(1, realm_rank=2), _ch(2, realm_rank=1)]
    report = lint_chapters(chapters, cfg, realm_max=5, realm_range=(1, 3))
    ids = [i.rule_id for i in report.issues]
    assert "REALM-01" in ids
    assert report.blocked


def test_realm_04_volume_gap():
    cfg = DabaiConfig()
    volumes = [
        {"volume_number": 1, "realm_start_rank": 1, "realm_end_rank": 2},
        {"volume_number": 2, "realm_start_rank": 1, "realm_end_rank": 3},
    ]
    report = lint_chapters([_ch(1)], cfg, volumes=volumes)
    assert any(i.rule_id == "REALM-04" for i in report.issues)


def test_db_09_missing_emotion_turn():
    cfg = DabaiConfig()
    report = lint_chapters([_ch(1, emotion_turn="")], cfg)
    assert any(i.rule_id == "DB-09" and i.severity == "high" for i in report.issues)


def test_clean_mock_shape_passes():
    """mock 样本形态应无 critical。"""
    cfg = DabaiConfig(volume_chapters=6)
    from dabai.mock_responses import get

    vols = get("volumes", cfg)
    chapters = get("chapter_outlines", cfg)
    levels = get("golden_finger", cfg)["power_ladder"]["levels"]  # 合并步 carrier
    ranks = [int(l["rank"]) for l in levels]
    v1 = vols[0]
    report = lint_chapters(
        chapters, cfg,
        realm_max=max(ranks),
        realm_range=(v1["realm_start_rank"], v1["realm_end_rank"]),
        volumes=vols,
    )
    assert not report.blocked
