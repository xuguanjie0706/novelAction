"""同人项目检测纯函数。"""
from types import SimpleNamespace

from app.services.bootstrap.fanfic_normalize import (
    is_fanfic_project,
    is_tomato_pace_project,
)


def test_is_fanfic_project_by_extra():
    p = SimpleNamespace(extra={"fanfic_positioning": {"source_work_title": "A"}})
    assert is_fanfic_project(p) is True


def test_is_tomato_pace_includes_fanfic():
    p = SimpleNamespace(
        extra={
            "fanfic_positioning": {"source_work_title": "A"},
            "positioning": {"pace_type": "fast", "bootstrap_mode": "fanfic"},
        }
    )
    assert is_tomato_pace_project(p) is True


def test_is_fanfic_false_for_plain_sequential():
    p = SimpleNamespace(extra={"positioning": {"pace_type": "normal"}})
    assert is_fanfic_project(p) is False
