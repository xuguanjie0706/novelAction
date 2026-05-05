"""封面生成失败时落盘调试包（原始 base64、网关元信息），便于线下对照网关返回。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from app.config import settings


def resolved_cover_debug_dir() -> Path:
    raw = (settings.COVER_DEBUG_DIR or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent / "data" / "covers" / "debug"


def _backend_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def write_cover_debug_bundle(
    *,
    project_id: str,
    stem_suffix: str,
    meta: dict[str, Any],
    raw_b64: Optional[str] = None,
    image_url: Optional[str] = None,
    upstream_response_text: Optional[str] = None,
    decoded_bytes: Optional[bytes] = None,
) -> str:
    """
    写入调试目录，返回相对后端根目录的路径（POSIX），供入库到 CoverImageCallLog.debug_bundle_rel_path。

    优先保存网关原始 base64（若存在）；过大亦完整写入，便于本地用 openssl/base64 工具重放。
    """
    base = resolved_cover_debug_dir()
    stem = f"{project_id}_{stem_suffix}_{uuid4().hex[:8]}"
    d = base / stem
    d.mkdir(parents=True, exist_ok=True)

    meta_path = d / "meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    if raw_b64 is not None:
        (d / "payload.b64.txt").write_text(raw_b64, encoding="utf-8")
    if image_url:
        (d / "image_url.txt").write_text(image_url, encoding="utf-8")
    if upstream_response_text is not None:
        (d / "upstream_response.txt").write_text(
            upstream_response_text[:500_000],
            encoding="utf-8",
            errors="replace",
        )
    if decoded_bytes is not None:
        (d / "decoded_attempt.bin").write_bytes(decoded_bytes[:50_000_000])

    abs_d = d.resolve()
    root = _backend_root().resolve()
    try:
        return abs_d.relative_to(root).as_posix()
    except ValueError:
        return str(abs_d)


def debug_stem_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
