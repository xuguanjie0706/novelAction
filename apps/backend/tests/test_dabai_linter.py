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


def test_clean_outline_shape_passes():
    """合规章纲形态（境界单调不退、转折拍齐全）应无 critical 阻断。"""
    cfg = DabaiConfig(volume_chapters=6)
    # 自包含合规样本：6 章境界 1→1→2→2→3→3 单调爬升，第5章大爆点。
    realm_by_ch = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
    chapters = [
        _ch(
            n,
            realm_rank=realm_by_ch[n],
            is_big_beat=(n == 5),
            shuang_type=["打脸", "升级", "获宝", "扮猪吃虎", "群嘲反转", "扬名"][n - 1],
        )
        for n in range(1, 7)
    ]
    volumes = [{"volume_number": 1, "realm_start_rank": 1, "realm_end_rank": 3}]
    report = lint_chapters(
        chapters, cfg,
        realm_max=3,
        realm_range=(1, 3),
        volumes=volumes,
    )
    assert not report.blocked
