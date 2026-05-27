"""storyline_drift 单元测试。"""

from types import SimpleNamespace

from app.services.ai.storyline_drift import beat_match_score, build_weave_matrix_overview


def test_beat_match_score_similar():
    assert beat_match_score("初遇误会", "初遇误会升级") > 0.3
    assert beat_match_score("完全不同", "另一件事") < 0.3


def test_build_weave_matrix_overview_empty_db():
    class FakeQ:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def all(self):
            return []

    class FakeDB:
        def query(self, model):
            return FakeQ()

    out = build_weave_matrix_overview(FakeDB(), "pid")
    assert out["n_volumes"] >= 1
    assert out["storylines"] == []
