"""AI 封面：压缩为 WebP，落本地磁盘或上传腾讯云 COS。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from app.config import settings
from app.services.tencent_cos import (
    cos_cover_storage_enabled,
    normalized_cover_storage_backend,
    upload_cover_webp,
)


def resolved_cover_storage_dir() -> Path:
    raw = (settings.COVER_STORAGE_DIR or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    # apps/backend/app/services/ -> backend/
    return Path(__file__).resolve().parent.parent.parent / "data" / "covers"


def ensure_cover_storage_dir() -> Path:
    d = resolved_cover_storage_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def compress_cover_webp_bytes(image_bytes: bytes) -> bytes:
    """将原始图片字节缩放、压缩为 WebP 字节。"""
    max_edge = max(64, min(settings.COVER_MAX_EDGE, 4096))
    q = max(30, min(settings.COVER_WEBP_QUALITY, 100))

    try:
        im = Image.open(BytesIO(image_bytes))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"无法解析图片数据：{e}") from e

    if im.mode not in ("RGB", "RGBA"):
        if im.mode == "P" and "transparency" in im.info:
            im = im.convert("RGBA")
        else:
            im = im.convert("RGB")

    im.thumbnail((max_edge, max_edge), _resample())

    buf = BytesIO()
    save_kw = {"format": "WEBP", "quality": q, "method": 4}
    im.save(buf, **save_kw)
    return buf.getvalue()


def _save_cover_webp_local(project_id: str, webp_bytes: bytes) -> str:
    d = ensure_cover_storage_dir()
    out = d / f"{project_id}.webp"
    out.write_bytes(webp_bytes)
    return f"/api/v1/covers/files/{project_id}.webp"


def compress_and_save_cover_webp(project_id: str, image_bytes: bytes) -> str:
    """
    压缩为 WebP 并持久化；后端由 COVER_STORAGE_BACKEND 决定（默认 local 磁盘）。

    - local：写入 data/covers，返回 /api/v1/covers/files/...
    - cos：上传腾讯云桶，返回 https 公网 URL
    """
    # 非法配置在此抛出，避免静默落错盘
    normalized_cover_storage_backend()
    webp_bytes = compress_cover_webp_bytes(image_bytes)
    if cos_cover_storage_enabled():
        return upload_cover_webp(project_id, webp_bytes)
    return _save_cover_webp_local(project_id, webp_bytes)
