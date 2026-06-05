"""narrative_arcs 合并步骤校验单测。"""
from app.services.bootstrap.narrative_arc_gen import apply_ladder_boss_names
from app.services.bootstrap.steps.narrative_arcs import _validate_narrative_arcs


def test_validate_narrative_arcs_ok():
    data = {
        "emotion_arc": [{"vol_index": 0, "vol_title": "卷一"}],
        "villain_arc": [{"vol_index": 0, "villain_name": "赵凌霄"}],
    }
    em, vil, err = _validate_narrative_arcs(data)
    assert err is None
    assert len(em) == 1 and len(vil) == 1


def test_validate_narrative_arcs_rejects_missing_villain():
    _, _, err = _validate_narrative_arcs({"emotion_arc": [{"vol_index": 0}]})
    assert err and "villain_arc" in err


def test_apply_ladder_boss_names():
    arc = [{"vol_index": 1, "villain_name": "旧名"}]
    ladder = [{"vol_index": 1, "boss_name": "厉九幽"}]
    out = apply_ladder_boss_names(arc, ladder)
    assert out[0]["villain_name"] == "厉九幽"
