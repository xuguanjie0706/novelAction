"""管理端：根据 cover_image_call_logs 解析可展示的图片字节。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import httpx

from app.models.cover_image_call_log import CoverImageCallLog
from app.services.cover_generate_debug import resolved_cover_debug_dir
from app.services.cover_storage import resolved_cover_storage_dir


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _safe_debug_bundle_dir(rel: Optional[str]) -> Optional[Path]:
    if not rel or not str(rel).strip():
        return None
    root = _backend_root().resolve()
    p = (root / str(rel).strip().lstrip("/")).resolve()
    try:
        p.relative_to(resolved_cover_debug_dir().resolve())
    except ValueError:
        return None
    return p if p.is_dir() else None


def _mime_from_magic(blob: bytes) -> str:
    from app.routers.cover_b64_decode import image_magic_kind

    k = image_magic_kind(blob)
    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
        "bmp": "image/bmp",
        "iso_bmff": "image/heif",
    }.get(k or "", "application/octet-stream")


def _read_local_cover_file(cover_api_path: str) -> Optional[Tuple[bytes, str]]:
    """cover_api_path 形如 /api/v1/covers/files/{id}.webp"""
    prefix = "/api/v1/covers/files/"
    if not cover_api_path.startswith(prefix):
        return None
    name = cover_api_path[len(prefix) :].strip().lstrip("/")
    if not name or "/" in name or ".." in name:
        return None
    p = resolved_cover_storage_dir() / name
    try:
        p.resolve().relative_to(resolved_cover_storage_dir().resolve())
    except ValueError:
        return None
    if not p.is_file():
        return None
    return p.read_bytes(), "image/webp"


def resolve_log_preview_image(row: CoverImageCallLog) -> Tuple[bytes, str]:
    """
    返回 (bytes, media_type)。若无可用图片则抛 FileNotFoundError。
    """
    if row.result_cover_url:
        url = (row.result_cover_url or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.get(url)
            if r.status_code >= 400:
                raise FileNotFoundError("remote preview failed")
            ct = (r.headers.get("content-type") or "").split(";")[0].strip() or _mime_from_magic(r.content)
            return r.content, ct
        local = _read_local_cover_file(url)
        if local:
            return local

    bundle = _safe_debug_bundle_dir(row.debug_bundle_rel_path)
    if bundle is not None:
        dec = bundle / "decoded_attempt.bin"
        if dec.is_file():
            raw = dec.read_bytes()
            return raw, _mime_from_magic(raw)
        b64f = bundle / "payload.b64.txt"
        if b64f.is_file():
            from app.routers.cover_b64_decode import decode_b64_image_payload

            txt = b64f.read_text(encoding="utf-8", errors="replace")
            raw = decode_b64_image_payload(txt)
            return raw, _mime_from_magic(raw)

    raise FileNotFoundError("no preview for log")
