"""同人立项 schema 校验。"""
from app.schemas.bootstrap_fanfic_positioning import try_validate_fanfic_positioning


def test_validate_fanfic_positioning_ok():
    raw = {
        "source_work_title": "测试原著",
        "fanfic_trope": "transmigration",
        "fanfic_trope_label": "穿书",
        "core_satisfaction": "看主角用剧情知识打脸反派",
        "fan_expectation": "磕原著 CP 吃到新糖",
        "canon_fidelity": "medium",
        "platform_tags": ["穿书", "同人", "打脸"],
        "algo_hook": "穿成炮灰前妻，开局就被休",
        "ooc_taboos": ["主角突然圣母"],
        "differentiation": "第一章就改命",
        "taboo_check": "否",
    }
    data, err = try_validate_fanfic_positioning(raw)
    assert err is None
    assert data is not None
    assert data["fanfic_trope"] == "transmigration"


def test_validate_fanfic_positioning_missing_field():
    raw = {"source_work_title": "x", "fanfic_trope": "au"}
    data, err = try_validate_fanfic_positioning(raw)
    assert data is None
    assert err
