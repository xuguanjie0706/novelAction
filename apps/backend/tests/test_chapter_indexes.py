from app.routers.chapter_indexes import get_chapter_index


class FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *conditions):
        return self

    def first(self):
        return self._result


class FakeDb:
    def __init__(self, result):
        self._result = result

    def query(self, model):
        return FakeQuery(self._result)


def test_get_chapter_index_returns_none_when_not_generated_yet():
    db = FakeDb(result=None)

    result = get_chapter_index("project-id", "chapter-id", db)

    assert result is None
