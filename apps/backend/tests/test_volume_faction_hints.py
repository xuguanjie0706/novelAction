"""volume_faction_hints 与 consistency_scan 势力裁决分流测试。"""

from types import SimpleNamespace

from app.services.bootstrap.steps.consistency_scan import _VOLUME_LINT_HARD_TYPES
from app.services.bootstrap.volume_faction_hints import collect_faction_semantic_hints
from app.services.bootstrap.volume_entity_registry import lint_volume_entity_issues


def _fake_db_with_vol(vol_summary: str, factions: list[str]):
    vol = SimpleNamespace(
        title="第五卷",
        summary=vol_summary,
        conflict="",
        hook="",
        sort_order=4,
        phase="climax",
        extra={},
    )

    class FakeQuery:
        def __init__(self, items):
            self._items = items

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return self._items

        def first(self):
            return self._items[0] if self._items else None

    class FakeDB:
        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if name == "OutlineNode":
                return FakeQuery([vol])
            if name == "Faction":
                return FakeQuery([SimpleNamespace(name=n) for n in factions])
            if name == "Character":
                return FakeQuery([])
            if name == "PowerSystem":
                return FakeQuery([])
            return FakeQuery([])

    return FakeDB()


def test_lint_no_longer_emits_regex_faction_mismatch():
    """叙事短语误识别不应再直写 faction_mismatch issue。"""
    db = _fake_db_with_vol(
        "陆沉攻破神教圣殿，直面虚空真相的守门人。青云陆家等残余门阀肃清。",
        ["青云陆家", "圣瞳神教"],
    )
    ctx = {
        "faction_names": ["青云陆家", "圣瞳神教"],
        "power_level_names": [],
        "protagonist": "陆沉",
    }
    issues = lint_volume_entity_issues(db, "pid", ctx)
    faction_issues = [i for i in issues if i.get("type") == "faction_mismatch"]
    assert faction_issues == []


def test_collect_hints_still_surfaces_suspects_for_ai():
    """疑似项改作 AI 线索，不丢失供裁决的上下文。"""
    db = _fake_db_with_vol(
        "莫问天死前化作虚空之门。陆沉攻破神教圣殿。",
        ["青云陆家", "圣瞳神教"],
    )
    ctx = {"faction_names": ["青云陆家", "圣瞳神教"], "protagonist": "陆沉"}
    hints = collect_faction_semantic_hints(db, "pid", ctx)
    joined = " ".join(hints)
    assert "虚空之门" in joined or "神教圣殿" in joined or "前化作虚空之门" in joined


def test_structural_precheck_filters_volume_lint_types():
    """consistency_scan 只直写结构化 lint 类型。"""
    assert "faction_mismatch" not in _VOLUME_LINT_HARD_TYPES
    assert "villain_alignment" in _VOLUME_LINT_HARD_TYPES
