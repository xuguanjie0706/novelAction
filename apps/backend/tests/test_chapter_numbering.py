"""display_chapter_number：标题「第N章」优先，否则 sort_order+1。"""

import pytest

from app.utils.chapter_numbering import display_chapter_number


@pytest.mark.parametrize(
    "title,sort_order,expected",
    [
        ("第2章：黑鼎残魂", 2, 2),
        ("第02章 标题", 0, 2),
        ("  第3章", 5, 3),
        ("楔子", 0, 1),
        ("楔子", 2, 3),
        ("", None, 1),
        (None, 4, 5),
    ],
)
def test_display_chapter_number(title, sort_order, expected):
    assert display_chapter_number(title, sort_order) == expected
