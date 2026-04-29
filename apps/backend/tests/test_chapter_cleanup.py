from app.models import ChapterIndex, MemoryChunk
from app.routers.chapters import delete_chapter_artifacts


class FakeQuery:
    def __init__(self, model, calls):
        self.model = model
        self.calls = calls

    def filter(self, *conditions):
        self.calls.append(("filter", self.model, len(conditions)))
        return self

    def delete(self, synchronize_session=False):
        self.calls.append(("delete", self.model, synchronize_session))
        return 1


class FakeDb:
    def __init__(self):
        self.calls = []

    def query(self, model):
        self.calls.append(("query", model))
        return FakeQuery(model, self.calls)


def test_delete_chapter_artifacts_removes_memory_and_chapter_index():
    db = FakeDb()

    delete_chapter_artifacts(db, "project-id", "chapter-id")

    deleted_models = [call[1] for call in db.calls if call[0] == "delete"]
    assert deleted_models == [MemoryChunk, ChapterIndex]
