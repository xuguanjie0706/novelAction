"""PATCH /projects/{id} 应能合并写入 project.extra（如番茄绑定 fanqie_book_id）。"""

from types import SimpleNamespace

from app.schemas import ProjectUpdate


def test_project_update_schema_accepts_extra():
    payload = ProjectUpdate(extra={"fanqie_book_id": "7636438734480608281"})
    assert payload.extra == {"fanqie_book_id": "7636438734480608281"}


def test_merge_extra_patch_preserves_existing_keys():
    """模拟 update_project 对 extra 的浅合并逻辑。"""
    project = SimpleNamespace(extra={"positioning": {"pace_type": "fast"}, "writing_config": {"auto_quality_gate": True}})
    extra_patch = {"fanqie_book_id": "7636438734480608281", "fanqie_book_name": "万古焚炉"}

    extra = dict(project.extra) if isinstance(project.extra, dict) else {}
    extra.update(extra_patch)
    project.extra = extra

    assert project.extra["fanqie_book_id"] == "7636438734480608281"
    assert project.extra["fanqie_book_name"] == "万古焚炉"
    assert project.extra["positioning"] == {"pace_type": "fast"}
    assert project.extra["writing_config"]["auto_quality_gate"] is True
