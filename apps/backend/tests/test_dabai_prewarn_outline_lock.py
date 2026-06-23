"""导演单章纲境界锁后处理。"""
from types import SimpleNamespace

from app.services.dabai.lab_prewarn_outline_lock import (
    build_outline_cast_lock_block,
    extract_outline_cast_realms,
    sanitize_prewarn_outline_lock,
    sync_cast_realm_from_outline,
)


def _ch10():
    return SimpleNamespace(
        involved_characters=["李夜", "陈山", "赵狂"],
        witnesses=["陈山", "赵狂", "王铁柱"],
        yaqu_setup=(
            "外门小比开始，李夜作为收尸人被分配到生死擂台。"
            "对手是外门狂徒陈山（练气三层），陈山当众嘲讽李夜。"
        ),
        emotion_turn="陈山拔刀叫嚣要废李夜修为",
        yinbao="李夜身形一晃避开刀锋，万魂幡阴气戳丹田",
        shuang_payoff="陈山倒飞出台，丹田尽毁",
        end_hook="赵狂站起，杀意凝实",
    )


def test_extract_outline_cast_realms():
    locked = extract_outline_cast_realms(_ch10())
    assert locked.get("陈山") == 3


def test_sanitize_prewarn_clamps_seven_to_three():
    ch = _ch10()
    raw = {
        "beat_execution": {
            "yaqu": "陈山（练气期七层）挑衅李夜",
            "trigger": "陈山挥刀",
            "yinbao": "李夜秒杀",
            "payoff": "全场死寂",
            "hook": "赵狂起身",
        },
        "reminders": [
            "陈山的境界必须严格设定为练气期七层，不可写成练气期三层，突出越级秒杀",
            "赵狂只能在看台表现杀意",
        ],
        "setup_check": "练气三层秒杀练气七层，依据阴风步",
        "cast": [{"name": "陈山", "reason": "练气七层对手"}],
    }
    out = sanitize_prewarn_outline_lock(raw, ch)
    assert "七层" not in out["beat_execution"]["yaqu"]
    assert "三层" in out["beat_execution"]["yaqu"]
    assert len(out["reminders"]) == 1
    assert "赵狂" in out["reminders"][0]
    assert "七层" not in out["setup_check"]


def test_sync_cast_realm_from_outline_fixes_bootstrap():
    from types import SimpleNamespace
    from uuid import uuid4

    ch = SimpleNamespace(
        chapter_number=10,
        involved_characters=["李夜", "陈山"],
        witnesses=["王铁柱"],
        yaqu_setup="对手陈山（练气三层）挑衅",
        emotion_turn="",
        yinbao="",
        shuang_payoff="",
        end_hook="",
    )
    c = SimpleNamespace(
        name="陈山",
        role="反派",
        start_realm="练气期七层",
        extra={},
    )
    project = SimpleNamespace(
        characters=[
            SimpleNamespace(name="李夜", role="主角", start_realm="炼气境·第1层", extra={}),
            c,
        ],
        power_ladder={"levels": [{"name": "练气期", "rank": 1}]},
    )

    class FakeDb:
        def add(self, _): ...
        def flush(self): ...

    logs = sync_cast_realm_from_outline(FakeDb(), project, ch)  # type: ignore[arg-type]
    assert "七层" in logs[0]
    assert c.start_realm == "练气期三层"
    assert c.extra["debut_chapter"] == 10
