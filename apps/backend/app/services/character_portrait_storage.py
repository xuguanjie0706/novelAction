"""人物立绘雪碧图：压缩落盘，通过 /api/v1/character-portraits/files 静态访问。"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Tuple

from PIL import Image

from app.config import settings


def resolved_character_portrait_dir() -> Path:
    raw = (getattr(settings, "CHARACTER_PORTRAIT_STORAGE_DIR", None) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent / "data" / "character-portraits"


def ensure_character_portrait_dir() -> Path:
    d = resolved_character_portrait_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def _project_dir(project_id: str) -> Path:
    d = ensure_character_portrait_dir() / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_character_sprite_sheet(
    project_id: str,
    character_id: str,
    image_bytes: bytes,
    *,
    cols: int = 4,
    rows: int = 1,
) -> Tuple[str, str, dict]:
    """
    保存雪碧图 WebP，并从首帧裁切头像。

    Returns:
        (sprite_url, avatar_url, sprite_meta)
    """
    cols = max(1, min(cols, 8))
    rows = max(1, min(rows, 4))

    try:
        im = Image.open(BytesIO(image_bytes))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"无法解析图片数据：{e}") from e

    if im.mode not in ("RGB", "RGBA"):
        if im.mode == "P" and "transparency" in im.info:
            im = im.convert("RGBA")
        else:
            im = im.convert("RGB")

    max_edge = max(256, min(getattr(settings, "CHARACTER_PORTRAIT_MAX_EDGE", 1536), 4096))
    q = max(30, min(getattr(settings, "CHARACTER_PORTRAIT_WEBP_QUALITY", 85), 100))

    im.thumbnail((max_edge, max_edge), _resample())
    w, h = im.size
    frame_w = max(1, w // cols)
    frame_h = max(1, h // rows)

    out_dir = _project_dir(project_id)
    sprite_name = f"{character_id}_sprite.webp"
    avatar_name = f"{character_id}_avatar.webp"
    save_kw = {"format": "WEBP", "quality": q, "method": 4}
    im.save(out_dir / sprite_name, **save_kw)

    # 首帧作为列表头像
    avatar_box = (0, 0, min(frame_w, w), min(frame_h, h))
    avatar_im = im.crop(avatar_box)
    av_size = max(64, min(getattr(settings, "CHARACTER_PORTRAIT_AVATAR_EDGE", 256), 512))
    avatar_im.thumbnail((av_size, av_size), _resample())
    avatar_im.save(out_dir / avatar_name, **save_kw)

    base = f"/api/v1/character-portraits/files/{project_id}"
    sprite_url = f"{base}/{sprite_name}"
    avatar_url = f"{base}/{avatar_name}"
    meta = {
        "url": sprite_url,
        "avatar_url": avatar_url,
        "cols": cols,
        "rows": rows,
        "frame_count": cols * rows,
        "frame_width": frame_w,
        "frame_height": frame_h,
        "image_width": w,
        "image_height": h,
    }
    return sprite_url, avatar_url, meta
