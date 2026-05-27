"""
番茄作家后台封面上传（upload_pic_v1）及 thumb_uri 解析。
"""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import httpx

from app.models import Project
from app.services.cover_storage import resolved_cover_storage_dir
from app.services.fanqie.client import BASE, proxy_post_multipart

_PATH_UPLOAD_PIC = "/api/author/data/upload_pic_v1/v0"
_MAX_BYTES = 8 * 1024 * 1024
_ALLOWED_TYPES = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"})


def extract_thumb_uri(data: Any) -> str:
    """从番茄 upload_pic 响应 data 提取 pic_uri / thumb_uri。"""
    if isinstance(data, str):
        s = data.strip().strip('"')
        if s.startswith("novel-pic"):
            return s.split("?")[0]
        return s
    if isinstance(data, dict):
        for key in ("thumb_uri", "pic_uri", "uri", "path", "url", "thumb_url", "data"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().split("?")[0]
    return ""


async def upload_cover_image(
    image_bytes: bytes,
    filename: str,
    content_type: str | None = None,
    *,
    book_id: str = "",
    creds: dict | None = None,
) -> str:
    """上传封面到番茄 CDN，返回 thumb_uri（如 novel-pic-r/xxx）。"""
    if len(image_bytes) > _MAX_BYTES:
        raise ValueError(f"封面不能超过 {_MAX_BYTES // 1024 // 1024}MB")
    ct = (content_type or "").split(";")[0].strip().lower()
    if not ct or ct not in _ALLOWED_TYPES:
        ext = Path(filename or "cover.png").suffix.lower()
        ct = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/png")

    referer = f"{BASE}/main/writer/create?enter_from=home"
    if book_id.strip():
        referer = f"{BASE}/main/writer/book-info/{book_id.strip()}?type=1&isEdit=1"

    data = await proxy_post_multipart(
        _PATH_UPLOAD_PIC,
        files={"upfile": (filename or "cover.png", image_bytes, ct)},
        referer=referer,
        creds=creds,
    )
    thumb_uri = extract_thumb_uri(data)
    if not thumb_uri:
        raise ValueError(f"番茄封面上传成功但未返回 thumb_uri，原始 data: {data!r}")
    return thumb_uri


def _decode_data_url(url: str) -> tuple[bytes, str]:
    match = re.match(r"data:(image/[\w+.-]+);base64,(.+)", url, re.DOTALL)
    if not match:
        raise ValueError("无法解析 data URL 封面")
    return base64.b64decode(match.group(2)), match.group(1)


async def _fetch_http_image(url: str) -> tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise ValueError(f"下载封面失败 HTTP {resp.status_code}")
    ct = resp.headers.get("content-type", "image/png").split(";")[0]
    return resp.content, ct


def _read_local_cover_path(cover_url: str) -> tuple[bytes, str] | None:
    path_part = cover_url
    for prefix in ("/api/v1/covers/files/", "/api/v1/covers/", "/covers/"):
        if prefix in cover_url:
            path_part = cover_url.split(prefix, 1)[-1].split("?")[0]
            break
    if not path_part or path_part.startswith("http"):
        return None
    local = resolved_cover_storage_dir() / path_part
    if not local.is_file():
        return None
    return local.read_bytes(), "image/webp" if local.suffix == ".webp" else "image/png"


async def load_project_cover_bytes(project: Project) -> tuple[bytes, str, str]:
    """加载项目封面字节，返回 (bytes, content_type, filename)。"""
    url = (project.cover_url or "").strip()
    if not url:
        raise ValueError("项目尚未设置封面")

    if url.startswith("data:"):
        raw, ct = _decode_data_url(url)
        ext = "webp" if "webp" in ct else "png"
        return raw, ct, f"cover.{ext}"

    if url.startswith("http://") or url.startswith("https://"):
        raw, ct = await _fetch_http_image(url)
        return raw, ct, "cover.png"

    local = _read_local_cover_path(url)
    if local:
        raw, ct = local
        return raw, ct, Path(url).name or "cover.webp"

    if url.startswith("/"):
        raw, ct = await _fetch_http_image(f"http://127.0.0.1:9000{url}")
        return raw, ct, "cover.png"

    raise ValueError("无法读取项目封面")
