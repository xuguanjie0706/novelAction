"""腾讯云 COS：书籍封面等公开读静态资源上传。"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.config import settings


# 封面存储后端：默认本地磁盘；.env 中 COVER_STORAGE_BACKEND 切换
_LOCAL_ALIASES = frozenset({"local", "disk", "filesystem", "fs"})
_COS_ALIASES = frozenset({"cos", "bucket", "tencent", "tencent_cos"})


def normalized_cover_storage_backend() -> str:
    """
    返回 ``local`` 或 ``cos``。
    未配置或空字符串 → ``local``（本地磁盘，默认）。
    """
    raw = (settings.COVER_STORAGE_BACKEND or "local").strip().lower()
    if not raw or raw in _LOCAL_ALIASES:
        return "local"
    if raw in _COS_ALIASES:
        return "cos"
    allowed = sorted(_LOCAL_ALIASES | _COS_ALIASES)
    raise ValueError(
        f"无效的 COVER_STORAGE_BACKEND={settings.COVER_STORAGE_BACKEND!r}，"
        f"可选：{', '.join(allowed)}（默认 local）"
    )


def cos_cover_storage_enabled() -> bool:
    return normalized_cover_storage_backend() == "cos"


def _require_cos_config() -> None:
    missing: list[str] = []
    if not (settings.COS_SECRET_ID or "").strip():
        missing.append("COS_SECRET_ID")
    if not (settings.COS_SECRET_KEY or "").strip():
        missing.append("COS_SECRET_KEY")
    if not (settings.COS_BUCKET or "").strip():
        missing.append("COS_BUCKET")
    if not (settings.COS_REGION or "").strip():
        missing.append("COS_REGION")
    if missing:
        raise ValueError(f"封面 COS 未配置完整，请在 .env 设置：{', '.join(missing)}")


@lru_cache(maxsize=1)
def _cos_client():
    from qcloud_cos import CosConfig, CosS3Client

    scheme = (settings.COS_SCHEME or "https").strip().rstrip(":/")
    config = CosConfig(
        Region=(settings.COS_REGION or "").strip(),
        SecretId=(settings.COS_SECRET_ID or "").strip(),
        SecretKey=(settings.COS_SECRET_KEY or "").strip(),
        Scheme=scheme,
    )
    return CosS3Client(config)


def cover_object_key(project_id: str) -> str:
    """对象键：{COS_PREFIX}{project_id}.webp"""
    prefix = (settings.COS_PREFIX or "novel-covers/").strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    safe_id = str(project_id).strip().replace("/", "").replace("..", "")
    if not safe_id:
        raise ValueError("无效 project_id")
    return f"{prefix}{safe_id}.webp"


def public_url_for_key(key: str) -> str:
    """生成浏览器可直链的 HTTPS URL（支持自定义 CDN 域名）。"""
    key = key.lstrip("/")
    base = (settings.COS_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}/{key}"
    bucket = (settings.COS_BUCKET or "").strip()
    region = (settings.COS_REGION or "").strip()
    scheme = (settings.COS_SCHEME or "https").strip().rstrip(":/")
    return f"{scheme}://{bucket}.cos.{region}.myqcloud.com/{key}"


def upload_cover_webp(project_id: str, webp_bytes: bytes) -> str:
    """
    上传 WebP 封面到 COS（公有读），返回公网 URL。
    存储桶需开启公有读，或允许 put_object 时设置 ACL=public-read。
    """
    _require_cos_config()
    if not webp_bytes:
        raise ValueError("空图片数据")

    key = cover_object_key(project_id)
    client = _cos_client()
    client.put_object(
        Bucket=(settings.COS_BUCKET or "").strip(),
        Key=key,
        Body=webp_bytes,
        ContentType="image/webp",
        ACL="public-read",
        CacheControl="public, max-age=31536000",
    )
    return public_url_for_key(key)


def try_resolve_cos_key_from_url(url: str) -> Optional[str]:
    """从已知的 COS 公网 URL 反推 object key（管理端预览兜底）。"""
    u = (url or "").strip()
    if not u.startswith("http://") and not u.startswith("https://"):
        return None
    base = (settings.COS_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base and u.startswith(base + "/"):
        return u[len(base) + 1 :]
    bucket = (settings.COS_BUCKET or "").strip()
    region = (settings.COS_REGION or "").strip()
    if not bucket or not region:
        return None
    host = f"{bucket}.cos.{region}.myqcloud.com"
    for scheme in ("https://", "http://"):
        prefix = f"{scheme}{host}/"
        if u.startswith(prefix):
            return u[len(prefix) :]
    return None
