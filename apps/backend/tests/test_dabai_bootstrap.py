"""dabai Bootstrap / 一致性 / 模式判定测试。"""
from __future__ import annotations

from types import SimpleNamespace

from app.schemas.bootstrap_dabai_positioning import try_validate_dabai_positioning
from app.services.bootstrap.antagonist_roster import bind_volume_boss_from_roster
from app.services.bootstrap.steps.dabai.dabai_bootstrap_lint import run_dabai_bootstrap_lint
from app.services.bootstrap.steps.dabai.dabai_converge import (
    bind_ladder_boss_names_to_characters,
    coerce_dabai_ladder_raw,
    is_placeholder_boss_name,
    normalize_dabai_character_realm,
    normalize_dabai_character_role,
)
from app.utils.dabai_mode import is_dabai_project


class _FakeQuery:
    def __init__(self, volumes):
        self._volumes = volumes

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        return self._volumes


class _FakeDB:
    def __init__(self, volumes, *, chars=None):
        self._volumes = volumes
        self._chars = chars if chars is not None else []
        self.committed = False

    def query(self, model):
        from app.models import Character
        if model is Character:
            return _FakeQuery(self._chars)
        return _FakeQuery(self._volumes)

    def commit(self):
        self.committed = True


def test_dabai_positioning_resume_validate():
    raw = {
        "target_audience": "下沉市场小白",
        "shuang_pool": ["打脸", "升级"],
        "face_slap_frequency": "每2-3章一次",
        "golden_three_strategy": "第1章钩子第3章打脸",
        "pace_type": "fast",
        "taboo_lines": ["禁止文绉绉"],
        "core_satisfaction": "升级打脸",
    }
    data, err = try_validate_dabai_positioning(raw)
    assert err is None
    assert data is not None
    assert data["face_slap_pattern"] == "每2-3章一次"
    assert data["reference_works"]
    assert data["bootstrap_mode"] == "dabai"


    p = SimpleNamespace(extra={"bootstrap_mode": "dabai"})
    assert is_dabai_project(p) is True
    p2 = SimpleNamespace(extra={"positioning": {"bootstrap_mode": "dabai"}})
    assert is_dabai_project(p2) is True
    assert is_dabai_project(SimpleNamespace(extra={})) is False


def test_dabai_converge_ladder_and_volume_boss():
    assert is_placeholder_boss_name("卷1Boss")
    assert not is_placeholder_boss_name("赵无极")

    raw = coerce_dabai_ladder_raw([
        {"volume_number": 1, "boss_name": "卷1Boss", "boss_realm": "玄脉境"},
    ])
    assert raw[0]["vol_index"] == 0
    assert raw[0]["realm_at_climax"] == "玄脉境"

    chars = [
        {"name": "叶狂", "role": "主角"},
        {"name": "赵长老", "role": "打脸对象"},
    ]
    ladder = bind_ladder_boss_names_to_characters(raw, chars)
    assert ladder[0]["boss_name"] == "赵长老"

    ctx = {
        "antagonist_ladder": [
            {"vol_index": 0, "boss_name": "赵长老", "realm_at_climax": "玄脉境"},
        ],
        "char_name_to_id": {"赵长老": "c1"},
    }
    vol_extra: dict = {}
    bind_volume_boss_from_roster(0, {}, vol_extra, ctx)
    assert vol_extra["volume_boss"] == "赵长老"
    assert vol_extra["volume_boss_realm"] == "玄脉境"
    assert vol_extra["volume_boss_character_id"] == "c1"


def test_normalize_dabai_character_role():
    assert normalize_dabai_character_role("主角") == ("protagonist", "主角")
    assert normalize_dabai_character_role("打脸对象") == ("antagonist", "打脸对象")
    assert normalize_dabai_character_role("supporting") == ("supporting", None)
    assert normalize_dabai_character_role("女主") == ("supporting", "女主")


def test_normalize_dabai_character_realm():
    ctx = {"power_level_names": ["凡蜕境", "玄脉境", "灵罡境"], "power_level_registry": {}}
    assert normalize_dabai_character_realm("灵根尽碎（凡人）", ctx, is_protagonist=True) == "凡蜕境"
    assert normalize_dabai_character_realm("练气五重", ctx) == "凡蜕境"
    assert normalize_dabai_character_realm("筑基境", ctx) == "玄脉境"


def test_dabai_chapter_display_title_fallback():
    from app.services.bootstrap.steps.dabai.vol_chapter_plans_dabai import _chapter_display_title

    assert _chapter_display_title({"title": "神体觉醒"}) == "神体觉醒"
    assert _chapter_display_title({"shuang_payoff": "一拳轰碎妖兽野狗，肉身力量增加万斤"}) == "一拳轰碎妖兽野狗，肉身力量增加万斤"
    assert _chapter_display_title({}) == "未命名"


def test_dabai_bootstrap_lint_missing_map():
    vol = SimpleNamespace(
        sort_order=0, phase="opening", extra={"realm_start_rank": 1, "realm_end_rank": 2},
    )
    db = _FakeDB([vol])
    project = SimpleNamespace(id="p1", extra={})
    svc = SimpleNamespace(db=db)
    report = run_dabai_bootstrap_lint(svc, project, {})
    assert any(i["rule_id"] == "DBL-01" for i in report["issues"])
