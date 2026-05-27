"""
番茄草稿上传前置解析：卷 ID、item_id。

每章应绑定独立 item_id（存 Chapter.extra）；批量同步时不得复用
其他章已占用的草稿槽。
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.services.fanqie.client import proxy_get

_PATH_DRAFT_LIST = "/api/author/chapter/draft_list/v1"
_PATH_CHAPTER_LIST = "/api/author/chapter/chapter_list/v1"

_CH_NUM_RE = re.compile(r"^第(\d+)章")


def _norm_title(title: str) -> str:
    return (title or "").strip().replace("：", ":").replace(" ", "")


def _chapter_num(title: str) -> int | None:
    m = _CH_NUM_RE.match(_norm_title(title))
    return int(m.group(1)) if m else None


def _pick_item_by_exact_title(
    items: list[Any],
    chapter_title: str,
    exclude_item_ids: set[str],
) -> str:
    """仅标题完全一致时匹配（避免「第1章」误匹配「第10章」草稿）。"""
    want = _norm_title(chapter_title)
    if not want:
        return ""
    want_num = _chapter_num(chapter_title)
    for it in items:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("item_id") or "")
        if not iid or iid in exclude_item_ids:
            continue
        got = _norm_title(str(it.get("title") or ""))
        if want == got:
            return iid
        if want_num is not None:
            got_num = _chapter_num(str(it.get("title") or ""))
            if got_num == want_num and got.startswith(f"第{want_num}章"):
                return iid
    return ""


def _pick_empty_unnamed_slot(
    drafts: list[Any],
    exclude_item_ids: set[str],
) -> tuple[str, str]:
    """挑选未被占用的「未命名草稿」空槽（优先字数 0、最近修改）。"""
    unnamed: list[dict[str, Any]] = []
    for d in drafts:
        if not isinstance(d, dict):
            continue
        title = str(d.get("title") or "")
        iid = str(d.get("item_id") or "")
        if not iid or iid in exclude_item_ids:
            continue
        if d.get("index") == -1 or title in ("未命名草稿", "（无标题）", ""):
            unnamed.append(d)
    if not unnamed:
        return "", ""
    empty = [d for d in unnamed if int(d.get("word_number") or 0) == 0]
    pool = empty or unnamed
    best = max(pool, key=lambda d: int(d.get("modify_time") or 0))
    iid = str(best.get("item_id") or "")
    if iid:
        return iid, "已占用新的番茄「未命名草稿」空槽"
    return "", ""


async def _fetch_draft_list(book_id: str) -> list[Any]:
    try:
        data = await proxy_get(
            _PATH_DRAFT_LIST,
            {"book_id": book_id, "page_index": 0, "page_count": 50},
            referer=f"https://fanqienovel.com/main/writer/{book_id}/",
        )
    except Exception:
        return []
    drafts = data.get("draft_list") if isinstance(data, dict) else []
    return drafts if isinstance(drafts, list) else []


async def fetch_book_volume(book_id: str) -> tuple[str, str]:
    """从该书 draft_list / chapter_list 取默认卷。"""
    drafts = await _fetch_draft_list(book_id)
    if drafts and isinstance(drafts[0], dict):
        return (
            str(drafts[0].get("volume_id") or ""),
            str(drafts[0].get("volume_name") or ""),
        )

    try:
        data = await proxy_get(
            _PATH_CHAPTER_LIST,
            {"book_id": book_id, "page_index": 0, "page_count": 1},
            referer=f"https://fanqienovel.com/main/writer/{book_id}/",
        )
        items = data.get("item_list") if isinstance(data, dict) else []
        if items and isinstance(items[0], dict):
            return str(items[0].get("volume_id") or ""), ""
    except Exception:
        pass

    return "", ""


async def resolve_fanqie_item_id(
    book_id: str,
    chapter_title: str,
    stored_item_id: str = "",
    *,
    allow_unnamed_slot: bool = True,
    exclude_item_ids: set[str] | None = None,
) -> tuple[str, str]:
    """
    解析 cover_article 的 item_id。

    - 有 stored_item_id：仅更新本章已绑定的草稿
    - 无记录：标题精确匹配 → 空未命名槽；均不得占用 exclude_item_ids 中的槽
    """
    excluded = set(exclude_item_ids or ())
    if stored_item_id:
        if stored_item_id in excluded:
            return stored_item_id, "更新已同步的番茄草稿"
        return stored_item_id, "更新已同步的番茄草稿"

    drafts = await _fetch_draft_list(book_id)

    matched = _pick_item_by_exact_title(drafts, chapter_title, excluded)
    if matched:
        return matched, "匹配到同标题番茄草稿"

    if allow_unnamed_slot:
        iid, hint = _pick_empty_unnamed_slot(drafts, excluded)
        if iid:
            return iid, hint

    return "", ""


def fanqie_error_hint(code: int, msg: str) -> str:
    if code == -2004:
        return (
            f"{msg}（番茄 code=-2004）。"
            "请刷新 cover_article 完整 cURL 后重试；"
            "首次同步会自动调用 new_article 新建章节。"
        )
    return msg
