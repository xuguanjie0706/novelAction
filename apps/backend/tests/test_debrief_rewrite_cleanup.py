from types import SimpleNamespace
from uuid import uuid4

from app.models import Faction, Item, Skill
from app.routers.ai.debrief_asset_undo import (
    capture_project_asset_snapshot,
    restore_project_asset_snapshot,
)
from app.routers.ai.schemas import CharacterUpdate
from app.routers.chapter_helpers import (
    remove_chapter_character_derivatives,
    restore_character_from_debrief_snapshot,
)
from app.services.ai.narrative_knowledge import remove_chapter_narrative_knowledge


def test_character_update_accepts_realm_change_reason():
    update = CharacterUpdate(
        character_id="char-id",
        current_realm="筑基境",
        realm_change_reason="服下筑基丹后破开气海壁垒",
    )

    assert update.realm_change_reason == "服下筑基丹后破开气海壁垒"


def test_remove_chapter_character_derivatives_clears_all_chapter_scoped_entries():
    character = SimpleNamespace(
        extra={
            "debrief_realm_milestones": [
                {"chapter_id": "chapter-8", "realm_name": "筑基境"},
                {"chapter_id": "chapter-9", "realm_name": "金丹境"},
            ],
            "location_milestones": [
                {"chapter_id": "chapter-8", "location": "青云宗"},
                {"chapter_id": "chapter-9", "location": "北漠"},
            ],
            "unrelated": "keep",
        },
        arc_stages=[
            {"chapter_id": "chapter-8", "stage": "筑基境"},
            {"chapter_id": "chapter-9", "stage": "金丹境"},
        ],
        speech_kit={
            "signature_words": ["且慢"],
            "recent_evolution_notes": [
                {"chapter_id": "chapter-8", "note": "语气转冷"},
                {"chapter_id": "chapter-9", "note": "恢复克制"},
            ],
        },
        known_skills=[
            {"from_chapter_id": "chapter-8", "skill_name": "焚天掌"},
            {"from_chapter_id": "chapter-9", "skill_name": "踏雪步"},
        ],
        owned_items=[
            {"from_chapter_id": "chapter-8", "item_name": "筑基丹"},
            {"from_chapter_id": "chapter-9", "item_name": "玄铁剑"},
        ],
    )

    changed = remove_chapter_character_derivatives(character, "chapter-8")

    assert changed is True
    assert [m["chapter_id"] for m in character.extra["debrief_realm_milestones"]] == ["chapter-9"]
    assert [m["chapter_id"] for m in character.extra["location_milestones"]] == ["chapter-9"]
    assert character.extra["unrelated"] == "keep"
    assert [m["chapter_id"] for m in character.arc_stages] == ["chapter-9"]
    assert [m["chapter_id"] for m in character.speech_kit["recent_evolution_notes"]] == ["chapter-9"]
    assert [m["from_chapter_id"] for m in character.known_skills] == ["chapter-9"]
    assert [m["from_chapter_id"] for m in character.owned_items] == ["chapter-9"]


def test_restore_character_snapshot_restores_null_values_too():
    character = SimpleNamespace(
        current_realm="筑基境",
        current_location="青云宗",
        current_status="alive",
        realm_rank=2,
    )

    restore_character_from_debrief_snapshot(
        character,
        {
            "current_realm": None,
            "current_location": None,
            "current_status": "alive",
            "realm_rank": None,
        },
    )

    assert character.current_realm is None
    assert character.current_location is None
    assert character.current_status == "alive"
    assert character.realm_rank is None


def test_remove_chapter_narrative_knowledge_rebuilds_terms_and_beats():
    project = SimpleNamespace(extra={
        "narrative_knowledge": {
            "public_terms": ["天火", "玄门"],
            "protagonist_terms": ["天火"],
            "term_events": [
                {"chapter": 8, "public_terms": ["天火"], "protagonist_terms": ["天火"]},
                {"chapter": 9, "public_terms": ["玄门"], "protagonist_terms": []},
            ],
            "locked_plot_beats": [
                {"chapter": 8, "beat": "主角获得天火"},
                {"chapter": 9, "beat": "玄门追杀令下达"},
            ],
        },
        "other": "keep",
    })

    assert remove_chapter_narrative_knowledge(project, chapter_number=8) is True
    nk = project.extra["narrative_knowledge"]
    assert nk["public_terms"] == ["玄门"]
    assert nk["protagonist_terms"] == []
    assert [b["chapter"] for b in nk["locked_plot_beats"]] == [9]
    assert project.extra["other"] == "keep"


class _AssetQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_conditions):
        return self

    def all(self):
        return list(self.rows)


class _AssetDb:
    def __init__(self, rows_by_model):
        self.rows_by_model = rows_by_model
        self.deleted = []

    def query(self, model):
        return _AssetQuery(self.rows_by_model.get(model, []))

    def delete(self, row):
        self.deleted.append(row)


def test_asset_snapshot_restores_existing_and_removes_chapter_created_assets():
    project_id = uuid4()
    old_item = Item(
        id=uuid4(), project_id=project_id, name="玄铁剑", status="intact", extra={"keep": True},
    )
    db = _AssetDb({Item: [old_item], Skill: [], Faction: []})
    snapshot = capture_project_asset_snapshot(db, str(project_id))

    old_item.status = "destroyed"
    new_item = Item(
        id=uuid4(), project_id=project_id, name="旧稿宝珠", status="intact",
        extra={"source_chapter_id": "chapter-8"},
    )
    db.rows_by_model[Item].append(new_item)

    restore_project_asset_snapshot(db, str(project_id), snapshot, "chapter-8")

    assert old_item.status == "intact"
    assert old_item.extra == {"keep": True}
    assert db.deleted == [new_item]
