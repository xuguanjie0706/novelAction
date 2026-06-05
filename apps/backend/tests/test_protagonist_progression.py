"""protagonist_progression 单元测试。"""

from app.services.bootstrap.protagonist_progression import (
    apply_volume_protagonist_fields,
    build_protagonist_progression_prompt_block,
    compute_book_realm_endpoints,
    compute_vol_end_ranks,
    format_volume_realm_anchor_line,
)


def _sample_ctx():
    return {
        "protagonist": "林烬",
        "char_realms": {"林烬": "凝气境"},
        "power_level_names": ["凝气境", "筑基境", "灵台境", "金丹境", "命轮境", "化神境"],
        "power_level_registry": {},
        "power_systems_full": [
            {"axis_role": "primary", "protagonist_end_rank": 5},
        ],
    }


def test_compute_book_realm_endpoints_with_char_realms():
    """回归：char_realms 存在时不得 NameError（registry 须从 ctx 读取）。"""
    ctx = _sample_ctx()
    result = compute_book_realm_endpoints(ctx)
    assert result is not None
    start_rank, end_rank, names = result
    assert start_rank >= 1
    assert end_rank > start_rank
    assert names


def test_build_protagonist_progression_prompt_with_char_realms():
    block = build_protagonist_progression_prompt_block(_sample_ctx(), 5)
    assert "主角境界成长路线" in block


def test_compute_vol_end_ranks_monotonic():
    ranks = compute_vol_end_ranks(_sample_ctx(), 5)
    assert ranks is not None
    assert ranks[0] >= 0
    assert ranks[-1] == 5
    assert ranks == sorted(ranks)


def test_apply_volume_protagonist_fields_fallback():
    ctx = _sample_ctx()
    vol_extra: dict = {}
    apply_volume_protagonist_fields({}, vol_extra, 0, ctx, 5)
    assert vol_extra.get("protagonist_realm_start") == "凝气境"
    assert vol_extra.get("protagonist_realm_end")
    assert vol_extra.get("protagonist_realm_end_rank") is not None


def test_apply_volume_protagonist_fields_respects_ai():
    ctx = _sample_ctx()
    vol_extra: dict = {}
    apply_volume_protagonist_fields(
        {
            "protagonist_realm_start": "凝气境",
            "protagonist_realm_end": "筑基境",
        },
        vol_extra,
        0,
        ctx,
        5,
    )
    assert vol_extra["protagonist_realm_start"] == "凝气境"
    assert vol_extra["protagonist_realm_end"] == "筑基境"
    assert vol_extra["protagonist_realm_end_rank"] == 1


def test_format_volume_realm_anchor_line():
    line = format_volume_realm_anchor_line({
        "protagonist_realm_start": "凝气境",
        "protagonist_realm_end": "筑基境",
        "volume_boss_realm": "灵台境",
    })
    assert "凝气境→筑基境" in line
    assert "BOSS 灵台境" in line


def test_backfill_volume_protagonist_realms_idempotent(monkeypatch):
    """缺 protagonist_realm_* 的卷应被插值补全，且二次调用不再写入。"""
    from app.services.bootstrap import protagonist_progression as pp

    class _Vol:
        def __init__(self, extra=None):
            self.extra = extra if extra is not None else {}

    volumes = [_Vol({}), _Vol({})]
    ctx = _sample_ctx()

    class _Q:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            return volumes

    class _Db:
        def query(self, model):
            return _Q()

        def commit(self):
            pass

    monkeypatch.setattr(pp, "build_protagonist_backfill_ctx", lambda db, pid: ctx)
    n1 = pp.backfill_volume_protagonist_realms(_Db(), "pid")
    assert n1 == 2
    assert volumes[0].extra.get("protagonist_realm_end")
    n2 = pp.backfill_volume_protagonist_realms(_Db(), "pid")
    assert n2 == 0
