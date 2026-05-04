"""AI 封面：压缩后落盘，通过 /api/v1/covers/files 提供静态访问。"""
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.config import settings


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


def compress_and_save_cover_webp(project_id: str, image_bytes: bytes) -> str:
    """
    将原始图片字节缩放、压缩为 WebP 写入磁盘。
    返回前端可用的相对路径（同源 /api 代理下可直接作 img src）。
    """
    d = ensure_cover_storage_dir()
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

    out = d / f"{project_id}.webp"
    save_kw = {"format": "WEBP", "quality": q, "method": 4}
    if im.mode == "RGBA":
        im.save(out, **save_kw)
    else:
        im.save(out, **save_kw)

    return f"/api/v1/covers/files/{project_id}.webp"
