"""
番茄新建章节：先 new_article 分配 item_id，再 cover_article 写入标题与正文。

与作家后台「新建章节」一致（Referer: enter_from=newchapter_0）。
"""
from __future__ import annotations

from typing import Any

from app.services.fanqie.client import BASE, proxy_post

_PATH_NEW_ARTICLE = "/api/author/article/new_article/v0/"


def _new_chapter_referer(book_id: str) -> str:
    return f"{BASE}/main/writer/{book_id}/publish/?enter_from=newchapter_0"


def _extract_new_item_id(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    val = data.get("item_id")
    return str(val) if val else ""


async def create_fanqie_new_article(
    *,
    book_id: str,
    volume_id: str,
    volume_name: str = "",
) -> str:
    """
    调用 new_article/v0，返回新章节 item_id（供 cover_article 使用）。

    Raises:
        ValueError: 接口未返回 item_id。
    """
    form: dict[str, str] = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": book_id,
        "volume_id": volume_id,
    }
    if volume_name.strip():
        form["volume_name"] = volume_name.strip()
    data = await proxy_post(
        _PATH_NEW_ARTICLE,
        form,
        referer=_new_chapter_referer(book_id),
    )
    item_id = _extract_new_item_id(data)
    if not item_id:
        raise ValueError("番茄 new_article 未返回 item_id，请刷新凭据后重试")
    return item_id
