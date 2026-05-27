"""番茄封面图代理：带作家 Cookie/Referer 拉取，供创作端同源展示。"""
from __future__ import annotations

from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app.services.fanqie.client import BASE, USER_AGENT, require_creds

_BYTEIMG_PREFIXES = (
    "https://p6-novel.byteimg.com/obj/",
    "https://p3-novel.byteimg.com/obj/",
    "https://p9-novel.byteimg.com/obj/",
)


def cover_proxy_path(*, url: str = "", thumb_uri: str = "") -> str | None:
    """生成创作端可用的同源封面路径。"""
    u = (url or "").strip()
    if u.startswith("http"):
        return f"/api/v1/fanqie/cover-image?url={quote(u, safe='')}"
    uri = (thumb_uri or "").strip()
    if uri and not uri.startswith("http"):
        return f"/api/v1/fanqie/cover-image?thumb_uri={quote(uri, safe='')}"
    return None


def _thumb_uri_to_urls(thumb_uri: str) -> list[str]:
    uri = thumb_uri.strip().lstrip("/")
    if not uri:
        return []
    urls = [f"{prefix}{uri}" for prefix in _BYTEIMG_PREFIXES]
    if uri.startswith("novel-pic"):
        urls.append(f"https://p6-novel.byteimg.com/obj/{uri}")
    return urls


async def fetch_cover_image(*, url: str = "", thumb_uri: str = "") -> tuple[bytes, str]:
    """
  拉取封面二进制。

  Returns:
      (body, content_type)
  """
    creds = require_creds()
    headers = {
        "user-agent": USER_AGENT,
        "referer": f"{BASE}/main/writer/book-manage",
        "accept": "image/*,*/*",
        "cookie": creds.get("cookies", ""),
    }
    candidates: list[str] = []
    if url.strip().startswith("http"):
        candidates.append(url.strip())
    candidates.extend(_thumb_uri_to_urls(thumb_uri))

    if not candidates:
        raise HTTPException(status_code=400, detail="缺少 url 或 thumb_uri")

    last_status = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        for target in candidates:
            try:
                resp = await client.get(target, headers=headers)
            except httpx.TimeoutException:
                continue
            last_status = resp.status_code
            if resp.status_code == 200 and resp.content:
                ct = resp.headers.get("content-type", "image/jpeg").split(";")[0]
                return resp.content, ct or "image/jpeg"

    raise HTTPException(
        status_code=502,
        detail=f"封面拉取失败（最近 HTTP {last_status}），签名可能已过期，请刷新书单",
    )
