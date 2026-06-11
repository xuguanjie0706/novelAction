"""dabai 实验书架卷纲质检（lab_outline_lint）。"""
from app.models.dabai import DabaiProject
from app.services.dabai.lab_outline_lint import _realm03_issues, cfg_from_project


def _ch(num: int, **kw) -> dict:
    base = {
        "chapter_number": num,
        "shuang_type": "打脸",
        "yaqu_setup": "被羞辱",
        "emotion_turn": "从隐忍→听到辱及亡母（触发）→杀意上涌",
        "shuang_payoff": "当众打脸",
        "witnesses": ["路人"],
        "end_hook": "更强敌人现身",
        "new_info_count": 1,
        "is_big_beat": False,
        "realm_rank": 1,
    }
    base.update(kw)
    return base


def test_realm03_supplemental_per_volume():
    volumes = [
        {"volume_number": 1, "planned_chapters": 2, "realm_start_rank": 1, "realm_end_rank": 2},
        {"volume_number": 2, "planned_chapters": 2, "realm_start_rank": 3, "realm_end_rank": 4},
    ]
    ch_dicts = [_ch(1, realm_rank=2), _ch(2, realm_rank=2), _ch(3, realm_rank=2), _ch(4, realm_rank=4)]
    issues = _realm03_issues(ch_dicts, volumes)
    assert any(i.rule_id == "REALM-03" and i.chapter == 3 for i in issues)


def test_cfg_from_project_reads_meta():
    p = DabaiProject(logline="测试", meta={"volume_chapters": 45, "big_beat_every": 7})
    cfg = cfg_from_project(p)
    assert cfg.volume_chapters == 45
    assert cfg.big_beat_every == 7
