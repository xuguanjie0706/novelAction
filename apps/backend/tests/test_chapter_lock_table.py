"""情节锁定表：规则检测与预警合并。"""
from app.services.ai.chapter_lock_table import (
    _detect_foreshadow_conflicts,
    merge_lock_table_into_warn_result,
)


def test_foreshadow_conflict_yaolao_already_awake():
    corpus = "萧炎回到房间。老师，看了这么久的戏，也该醒了吧？药老被迫现身"
    foreshadow = "加热[戒指中的异动，药老的一丝意识开始苏醒]"
    conflicts = _detect_foreshadow_conflicts(corpus, foreshadow)
    assert len(conflicts) >= 1
    assert any("药老" in c.get("reason", "") for c in conflicts)


def test_merge_lock_adds_critical_risk():
    lock = {
        "has_prev": True,
        "prev_chapter_number": 1,
        "current_chapter_number": 2,
        "locked_beats": ["章末状态：药老已对话"],
        "forbidden_replays": ["禁止再次药老初次苏醒"],
        "outline_conflicts": [
            {
                "field": "foreshadow",
                "outline_text": "药老将苏醒",
                "reason": "上章药老已交流，本章 foreshadow 冲突",
            }
        ],
        "prev_tail_anchor": "也该醒了吧",
    }
    warn = {"ok": True, "risk_count": 0, "risks": [], "reminders": []}
    out = merge_lock_table_into_warn_result(warn, lock)
    assert out["ok"] is False
    assert out["risk_count"] >= 1
    assert out["chapter_lock_table"]["has_prev"] is True
    assert any(r.get("severity") == "critical" for r in out["risks"])
