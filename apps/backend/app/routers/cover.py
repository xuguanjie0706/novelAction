"""
封面生成路由

POST /api/v1/projects/{project_id}/cover/generate
  - 调用图片类型 LlmProvider（provider_type='image'）的 /v1/images/generations 接口
  - 默认将结果压缩为 WebP 落盘，返回短路径 cover_url（/api/v1/covers/files/...）供入库与 <img src>
  - store_compressed=false 时仍返回 data_url / image_url（大响应）
  - 每次调用写入 cover_image_call_logs；网关成功但解码/压缩失败时落盘 data/covers/debug/<stem>/（meta.json + payload.b64.txt 等）

POST /api/v1/projects/{project_id}/cover/upload
  - multipart 字段 file：用户上传的封面图（JPG/PNG/WebP/GIF），压缩为 WebP 落盘并返回 cover_url

GET  /api/v1/cover/image-providers
  - 返回所有 enabled + provider_type='image' 的提供者列表（前端选择用）
"""
import base64
import json
import logging
import re
import time
import zlib
from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import httpx
from PIL import Image
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CoverImageCallLog, Project
from app.models.llm_provider import LlmProvider
from app.services.cover_generate_debug import debug_stem_timestamp, write_cover_debug_bundle
from app.services.cover_storage import compress_and_save_cover_webp
from app.services.llm_config import normalize_openai_base_url

router = APIRouter(tags=["cover"])
logger = logging.getLogger(__name__)

MAX_COVER_UPLOAD_BYTES = 15 * 1024 * 1024


# ── Schema ─────────────────────────────────────────────────────────────────

class ImageProviderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: UUID
    name: str
    model_name: str


class CoverGenerateIn(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    llm_provider_id: UUID
    prompt: str = Field(..., max_length=2000)
    size: str = Field("1024x1024", pattern=r"^\d+x\d+$")
    quality: str = Field("standard", pattern=r"^(standard|hd)$")
    store_compressed: bool = True


class CoverGenerateOut(BaseModel):
    """store_compressed 时优先返回 cover_url；否则为 data URL 或外链。"""
    cover_url: Optional[str] = None  # 站内静态路径，可写入 projects.cover_url
    data_url: Optional[str] = None   # data:image/png;base64,…  (b64_json 模式)
    image_url: Optional[str] = None  # 部分 provider 直接返回 URL


@dataclass
class CoverGenGatewayCall:
    """图片网关一次调用的结果（供路由与 cover_image_call_logs 共用）。"""

    success: bool
    out: Optional[CoverGenerateOut] = None
    elapsed_ms: int = 0
    http_status: int = 0
    gateway_url: str = ""
    error_user_message: str = ""
    upstream_response_text: Optional[str] = None


def _normalize_b64_json_from_provider(raw: Optional[str]) -> str:
    """
    部分网关/代理商在 b64_json 里直接塞完整 data URL，或带首尾引号；
    若再包一层 data:image/png;base64,... 会导致逗号后不是纯 base64。此处剥到最内层 payload。
    """
    if raw is None:
        return ""
    s = "".join(str(raw).split()).strip("\ufeff\u200b\u200c\u200d")
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1]
    # 可能多层 data:*;base64, 嵌套
    for _ in range(4):
        m = re.match(r"^data:[^;]+;base64,(.+)$", s, re.IGNORECASE | re.DOTALL)
        if not m:
            break
        inner = m.group(1).strip()
        if inner == s:
            break
        s = inner
    return s


# ── Helpers ────────────────────────────────────────────────────────────────

def _format_gateway_url(base_url: str) -> str:
    u = normalize_openai_base_url(base_url).rstrip("/")
    parsed = urlparse(u)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/v1/images/generations"
    return f"{u}/images/generations"


def _execute_images_generations(
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    size: str,
    quality: str,
) -> CoverGenGatewayCall:
    """
    调用 OpenAI 兼容的 /v1/images/generations。
    不抛 HTTPException，由路由统一写审计日志后再映射为 HTTP 错误。
    """
    gateway_url = _format_gateway_url(base_url)
    url = normalize_openai_base_url(base_url).rstrip("/") + "/images/generations"
    key = (api_key or "").strip() or "not-required"
    t0 = time.monotonic()

    payload = {
        "model": model_name,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "response_format": "b64_json",
    }

    try:
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return CoverGenGatewayCall(
            False,
            elapsed_ms=elapsed_ms,
            gateway_url=gateway_url,
            error_user_message="图片生成超时（>120s），请稍后重试",
        )
    except httpx.ConnectError as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return CoverGenGatewayCall(
            False,
            elapsed_ms=elapsed_ms,
            gateway_url=gateway_url,
            error_user_message=f"无法连接图片模型网关：{e}",
        )

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    if resp.status_code >= 400:
        detail = ""
        try:
            err = resp.json()
            detail = err.get("error", {}).get("message") or str(err)
        except Exception:
            detail = resp.text[:400]
        return CoverGenGatewayCall(
            False,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message=f"图片模型返回错误：{detail}",
            upstream_response_text=resp.text[:50_000],
        )

    try:
        data = resp.json()
    except Exception:
        return CoverGenGatewayCall(
            False,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message="图片模型返回非 JSON 响应",
            upstream_response_text=resp.text[:50_000],
        )

    items = data.get("data") or []
    if not items:
        return CoverGenGatewayCall(
            False,
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            gateway_url=gateway_url,
            error_user_message="图片模型未返回图片数据",
            upstream_response_text=json.dumps(data, ensure_ascii=False)[:50_000],
        )

    item = items[0]
    if b64 := item.get("b64_json"):
        clean = _normalize_b64_json_from_provider(b64)
        return CoverGenGatewayCall(
            True,
            out=CoverGenerateOut(data_url=f"data:image/png;base64,{clean}"),
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            gateway_url=gateway_url,
        )
    if img_url := item.get("url"):
        return CoverGenGatewayCall(
            True,
            out=CoverGenerateOut(image_url=img_url),
            elapsed_ms=elapsed_ms,
            http_status=resp.status_code,
            gateway_url=gateway_url,
        )

    return CoverGenGatewayCall(
        False,
        elapsed_ms=elapsed_ms,
        http_status=resp.status_code,
        gateway_url=gateway_url,
        error_user_message="图片模型返回格式未知（无 b64_json 也无 url）",
        upstream_response_text=json.dumps(data, ensure_ascii=False)[:50_000],
    )


def _raw_b64_from_out(out: CoverGenerateOut) -> Optional[str]:
    if out.data_url and "," in out.data_url:
        inner = out.data_url.split(",", 1)[1]
        clean = _normalize_b64_json_from_provider(inner)
        return clean or None
    return None


def _upstream_failure_status(call: CoverGenGatewayCall) -> str:
    msg = call.error_user_message
    if "超时" in msg:
        return "upstream_network"
    if "无法连接" in msg:
        return "upstream_network"
    if call.http_status and call.http_status >= 400:
        return "upstream_http"
    if "未返回图片数据" in msg:
        return "upstream_empty"
    if "非 JSON" in msg or "格式未知" in msg:
        return "upstream_bad_json"
    return "upstream_error"


def _http_status_for_gateway_failure(call: CoverGenGatewayCall) -> int:
    if "超时" in call.error_user_message:
        return 504
    if "无法连接" in call.error_user_message:
        return 502
    if call.http_status and 400 <= call.http_status < 600:
        return call.http_status
    return 502


def _insert_cover_image_log(
    db: Session,
    *,
    project: Project,
    provider: LlmProvider,
    payload: CoverGenerateIn,
    status: str,
    duration_ms: int,
    response_kind: str,
    gateway_url: str,
    http_status: Optional[int],
    error_message: Optional[str],
    debug_bundle_rel_path: Optional[str],
    result_cover_url: Optional[str] = None,
) -> None:
    db.add(
        CoverImageCallLog(
            project_id=project.id,
            llm_provider_id=provider.id,
            provider_name=provider.name,
            model_name=provider.model_name,
            prompt=payload.prompt,
            size=payload.size,
            quality=payload.quality,
            store_compressed=payload.store_compressed,
            status=status,
            http_status=http_status,
            error_message=error_message,
            duration_ms=duration_ms,
            response_kind=response_kind,
            gateway_url=gateway_url,
            debug_bundle_rel_path=debug_bundle_rel_path,
            result_cover_url=result_cover_url,
        )
    )
    db.commit()


def _try_write_debug_bundle(
    *,
    project_id: str,
    provider: LlmProvider,
    payload: CoverGenerateIn,
    gateway_url: str,
    status: str,
    duration_ms: int,
    response_kind: str,
    error_message: Optional[str],
    raw_b64: Optional[str] = None,
    image_url: Optional[str] = None,
    upstream_response_text: Optional[str] = None,
    decoded_bytes: Optional[bytes] = None,
) -> Optional[str]:
    try:
        return write_cover_debug_bundle(
            project_id=project_id,
            stem_suffix=debug_stem_timestamp(),
            meta={
                "project_id": project_id,
                "llm_provider_id": str(provider.id),
                "provider_name": provider.name,
                "model_name": provider.model_name,
                "gateway_url": gateway_url,
                "size": payload.size,
                "quality": payload.quality,
                "store_compressed": payload.store_compressed,
                "status": status,
                "duration_ms": duration_ms,
                "response_kind": response_kind,
                "error_message": error_message,
                "prompt": payload.prompt,
            },
            raw_b64=raw_b64,
            image_url=image_url,
            upstream_response_text=upstream_response_text,
            decoded_bytes=decoded_bytes,
        )
    except Exception:
        logger.exception("写入封面调试包失败")
        return None


def _image_magic_kind(blob: bytes) -> Optional[str]:
    """识别常见栅格图魔数；用于从多种 base64 纠错候选里挑出真图片。"""
    if len(blob) < 12:
        return None
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if blob.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if blob.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if blob.startswith(b"RIFF") and len(blob) >= 12 and blob[8:12] == b"WEBP":
        return "webp"
    if blob.startswith(b"BM"):
        return "bmp"
    # ISO BMFF（AVIF/HEIC 等）；能否打开取决于 Pillow 是否带对应解码器
    if len(blob) >= 12 and blob[4:8] == b"ftyp":
        return "iso_bmff"
    return None


def _base64_input_variants_extended(raw: str) -> List[str]:
    """
    尽可能覆盖网关脏数据：去空白、去多余 =、mod4 修边、首尾少量非字母数字垃圾。
    """
    s0 = "".join((raw or "").split()).strip("\ufeff\u200b\u200c\u200d")
    if not s0:
        return []
    seen: set[str] = set()
    out: List[str] = []

    def add(x: str) -> None:
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(s0)
    stripped_eq = s0.rstrip("=")
    if stripped_eq != s0:
        add(stripped_eq)
    n = len(s0)
    rem = n % 4
    if rem == 1:
        add(s0[:-1])
        add(s0[1:])
    elif rem == 2:
        add(s0[:-1])
        add(s0[1:])
    elif rem == 3:
        add(s0[:-1])
    for a in (1, 2, 3):
        if len(s0) > a + 48:
            add(s0[a:])
            add(s0[:-a])
    return out


def _pad_b64(s: str) -> str:
    pad = (4 - len(s) % 4) % 4
    return s + "=" * pad


def _try_b64decode_once(s: str) -> Optional[bytes]:
    """标准字母表 + url-safe 转写后解码。"""
    for alphabet in (
        s,
        s.translate(str.maketrans("-_", "+/")),
    ):
        padded = _pad_b64(alphabet)
        try:
            return base64.b64decode(padded, validate=False)
        except Exception:
            continue
    return None


def _try_urlsafe_b64decode(s: str) -> Optional[bytes]:
    t = s.strip()
    if not t:
        return None
    pad = (-len(t)) % 4
    if pad:
        t += "=" * pad
    try:
        return base64.urlsafe_b64decode(t)
    except Exception:
        return None


def _try_hex_decode(s: str) -> Optional[bytes]:
    t = re.sub(r"\s+", "", s)
    if len(t) < 200 or len(t) % 2 != 0:
        return None
    if not re.fullmatch(r"[0-9a-fA-F]+", t):
        return None
    try:
        return bytes.fromhex(t)
    except Exception:
        return None


def _extract_json_strings_for_image(obj: object, acc: List[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, str):
        if len(obj) > 80:
            acc.append(obj)
        return
    if isinstance(obj, dict):
        priority_keys = (
            "b64_json",
            "image",
            "image_base64",
            "base64",
            "data",
            "content",
            "result",
            "bytes",
            "file",
        )
        for k in priority_keys:
            v = obj.get(k)
            if isinstance(v, str) and len(v) > 32:
                acc.append(v)
        for v in obj.values():
            _extract_json_strings_for_image(v, acc, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:24]:
            _extract_json_strings_for_image(v, acc, depth + 1)


def _try_json_wrapped_payload(s: str) -> List[str]:
    t = s.strip()
    if not t.startswith("{"):
        return []
    try:
        obj = json.loads(t)
    except Exception:
        return []
    acc: List[str] = []
    _extract_json_strings_for_image(obj, acc)
    return acc


def _maybe_inflate(blob: bytes) -> List[bytes]:
    if len(blob) < 24:
        return []
    out: List[bytes] = []
    for wbits in (zlib.MAX_WBITS | 16, zlib.MAX_WBITS, -zlib.MAX_WBITS):
        try:
            d = zlib.decompress(blob, wbits=wbits)
            if len(d) > 80:
                out.append(d)
        except Exception:
            continue
    return out


def _slices_from_embedded_file_signatures(blob: bytes, max_slices: int = 16) -> List[bytes]:
    """二进制前部有垃圾前缀时，扫描常见图像魔数再切片。"""
    if len(blob) < 24:
        return []
    needles = (
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"GIF87a",
        b"GIF89a",
        b"RIFF",
        b"BM",
    )
    out: List[bytes] = []
    scan = blob[: min(len(blob), 262_144)]
    for needle in needles:
        start = 0
        found = 0
        while found < 4:
            idx = scan.find(needle, start)
            if idx < 0:
                break
            out.append(blob[idx:])
            start = idx + max(len(needle), 1)
            found += 1
            if len(out) >= max_slices:
                return out
    return out[:max_slices]


def _uniq_bytes(chunks: Iterable[bytes]) -> List[bytes]:
    seen: set[bytes] = set()
    out: List[bytes] = []
    for b in chunks:
        if b and b not in seen:
            seen.add(b)
            out.append(b)
    return out


def _strings_for_decode_from_raw(raw: str) -> List[str]:
    raw = _normalize_b64_json_from_provider(raw)
    acc: List[str] = [raw]
    acc.extend(_try_json_wrapped_payload(raw))
    seen: set[str] = set()
    out: List[str] = []
    for s in acc:
        c = _normalize_b64_json_from_provider(s)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _all_blobs_from_b64_string(s: str) -> List[bytes]:
    blobs: List[bytes] = []
    for variant in _base64_input_variants_extended(s):
        b = _try_b64decode_once(variant)
        if b is not None:
            blobs.append(b)
            continue
        b2 = _try_urlsafe_b64decode(variant)
        if b2 is not None:
            blobs.append(b2)
    hx = _try_hex_decode(s)
    if hx is not None:
        blobs.append(hx)
    return _uniq_bytes(blobs)


def _try_peel_textual_base64_layers(blob: bytes, max_rounds: int = 6) -> List[bytes]:
    """
    网关偶发「二次 base64」：解码后仍是文本再包一层。逐层剥开，返回链上每一层。
    """
    seen: set[bytes] = set()
    chain: List[bytes] = []
    cur: Optional[bytes] = blob
    for _ in range(max_rounds):
        if not cur or cur in seen:
            break
        seen.add(cur)
        chain.append(cur)
        if _image_magic_kind(cur):
            break
        txt: Optional[str] = None
        try:
            txt = cur.decode("utf-8")
        except Exception:
            try:
                txt = cur.decode("latin-1")
            except Exception:
                break
        nxt_str = _normalize_b64_json_from_provider(txt.strip())
        if not nxt_str or len(nxt_str) < 24:
            break
        nxt_bytes: Optional[bytes] = None
        for variant in _base64_input_variants_extended(nxt_str):
            nxt_bytes = _try_b64decode_once(variant) or _try_urlsafe_b64decode(variant)
            if nxt_bytes:
                break
        if not nxt_bytes or nxt_bytes == cur:
            break
        cur = nxt_bytes
    return chain


def _expand_blob_candidates(blob: bytes) -> List[bytes]:
    """解压、按魔数切片、与剥层结果一并展开。"""
    parts: List[bytes] = [blob]
    for c in _try_peel_textual_base64_layers(blob):
        parts.append(c)
        for inf in _maybe_inflate(c):
            parts.append(inf)
        for sl in _slices_from_embedded_file_signatures(c):
            parts.append(sl)
    for inf in _maybe_inflate(blob):
        parts.append(inf)
    for sl in _slices_from_embedded_file_signatures(blob):
        parts.append(sl)
    return _uniq_bytes(parts)


def _decode_b64_image_payload(raw: str) -> bytes:
    """
    多路径兜底：data URL 剥层、JSON 嵌套字段、扩展 base64 变体、urlsafe、hex、
    二次 base64 文本链、gzip/zlib、二进制内嵌扫描，最后用 PIL 验证。
    """
    candidates: List[bytes] = []
    for s in _strings_for_decode_from_raw(raw):
        if not s:
            continue
        for blob in _all_blobs_from_b64_string(s):
            candidates.extend(_expand_blob_candidates(blob))

    candidates = _uniq_bytes(candidates)

    if not candidates:
        raise ValueError("无法对网关返回的 payload 进行 base64 解码")

    def pil_verify(blob: bytes) -> Optional[bytes]:
        if len(blob) < 12:
            return None
        try:
            im = Image.open(BytesIO(blob))
            im.load()
            return blob
        except Exception:
            return None

    for blob in candidates:
        if _image_magic_kind(blob):
            got = pil_verify(blob)
            if got is not None:
                return got

    for blob in candidates:
        got = pil_verify(blob)
        if got is not None:
            return got

    head = candidates[0][:32]
    hint = f"（首 32 字节 hex：{head.hex()}）"
    raise ValueError(f"解码结果不是可识别的图片格式{hint}")


def _raw_bytes_from_generate_out(out: CoverGenerateOut) -> bytes:
    if out.data_url and "," in out.data_url:
        try:
            b64 = _normalize_b64_json_from_provider(out.data_url.split(",", 1)[1])
            return _decode_b64_image_payload(b64)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"解析 base64 图片失败：{e}") from e
    if out.image_url:
        try:
            with httpx.Client(timeout=60.0, follow_redirects=True) as client:
                r = client.get(out.image_url)
        except httpx.TimeoutException:
            raise HTTPException(504, "下载生成图超时") from None
        except httpx.ConnectError as e:
            raise HTTPException(502, f"无法下载生成图：{e}") from e
        if r.status_code >= 400:
            raise HTTPException(502, f"下载生成图失败：HTTP {r.status_code}")
        return r.content
    raise HTTPException(502, "未获得可保存的图片数据")


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/cover/image-providers", response_model=List[ImageProviderBrief])
def list_image_providers(db: Session = Depends(get_db)):
    """返回所有启用的图片类提供者，供前端下拉选择。"""
    rows = (
        db.query(LlmProvider)
        .filter(
            LlmProvider.enabled.is_(True),
            LlmProvider.provider_type == "image",
        )
        .order_by(LlmProvider.sort_order.asc(), LlmProvider.updated_at.desc())
        .all()
    )
    return [ImageProviderBrief(id=r.id, name=r.name, model_name=r.model_name) for r in rows]


@router.post("/projects/{project_id}/cover/upload", response_model=CoverGenerateOut)
async def upload_cover(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传本地图片作为封面，压缩为 WebP 后写入 data/covers。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(400, "空文件")
    if len(data) > MAX_COVER_UPLOAD_BYTES:
        raise HTTPException(400, f"文件过大，请上传小于 {MAX_COVER_UPLOAD_BYTES // (1024 * 1024)}MB 的图片")

    try:
        path = compress_and_save_cover_webp(str(project.id), data)
        return CoverGenerateOut(cover_url=path)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/projects/{project_id}/cover/generate", response_model=CoverGenerateOut)
def generate_cover(
    project_id: str,
    payload: CoverGenerateIn,
    db: Session = Depends(get_db),
):
    """
    用指定的图片提供者为项目生成封面。
    默认压缩为 WebP 落盘并返回 cover_url；前端可 PATCH /projects/{id} 将 cover_url 写入数据库。
    每次调用写入 cover_image_call_logs；解析/压缩失败时优先落盘 payload.b64.txt 便于回溯。
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    provider = (
        db.query(LlmProvider)
        .filter(
            LlmProvider.id == payload.llm_provider_id,
            LlmProvider.enabled.is_(True),
            LlmProvider.provider_type == "image",
        )
        .first()
    )
    if not provider:
        raise HTTPException(404, "找不到该图片提供者，请确认已在管理后台启用并设置为 image 类型")

    call = _execute_images_generations(
        base_url=provider.base_url,
        api_key=provider.api_key or "",
        model_name=provider.model_name,
        prompt=payload.prompt,
        size=payload.size,
        quality=payload.quality,
    )
    pid = str(project.id)

    if not call.success:
        st = _upstream_failure_status(call)
        dbg = _try_write_debug_bundle(
            project_id=pid,
            provider=provider,
            payload=payload,
            gateway_url=call.gateway_url,
            status=st,
            duration_ms=call.elapsed_ms,
            response_kind="none",
            error_message=call.error_user_message,
            upstream_response_text=call.upstream_response_text,
        )
        _insert_cover_image_log(
            db,
            project=project,
            provider=provider,
            payload=payload,
            status=st,
            duration_ms=call.elapsed_ms,
            response_kind="none",
            gateway_url=call.gateway_url,
            http_status=call.http_status or None,
            error_message=call.error_user_message,
            debug_bundle_rel_path=dbg,
            result_cover_url=None,
        )
        raise HTTPException(_http_status_for_gateway_failure(call), call.error_user_message)

    raw_out = call.out
    assert raw_out is not None
    raw_b64 = _raw_b64_from_out(raw_out)
    response_kind = "b64_json" if raw_b64 else "url"

    if not payload.store_compressed:
        preview_url = raw_out.image_url if raw_out.image_url else None
        _insert_cover_image_log(
            db,
            project=project,
            provider=provider,
            payload=payload,
            status="ok",
            duration_ms=call.elapsed_ms,
            response_kind=response_kind,
            gateway_url=call.gateway_url,
            http_status=call.http_status,
            error_message=None,
            debug_bundle_rel_path=None,
            result_cover_url=preview_url,
        )
        return raw_out

    try:
        blob = _raw_bytes_from_generate_out(raw_out)
    except HTTPException as e:
        detail = str(e.detail) if e.detail is not None else "解析或下载图片失败"
        dbg = _try_write_debug_bundle(
            project_id=pid,
            provider=provider,
            payload=payload,
            gateway_url=call.gateway_url,
            status="decode_error",
            duration_ms=call.elapsed_ms,
            response_kind=response_kind,
            error_message=detail,
            raw_b64=raw_b64,
            image_url=raw_out.image_url,
        )
        _insert_cover_image_log(
            db,
            project=project,
            provider=provider,
            payload=payload,
            status="decode_error",
            duration_ms=call.elapsed_ms,
            response_kind=response_kind,
            gateway_url=call.gateway_url,
            http_status=call.http_status,
            error_message=detail,
            debug_bundle_rel_path=dbg,
            result_cover_url=None,
        )
        raise

    try:
        path = compress_and_save_cover_webp(pid, blob)
    except ValueError as e:
        msg = str(e)
        dbg = _try_write_debug_bundle(
            project_id=pid,
            provider=provider,
            payload=payload,
            gateway_url=call.gateway_url,
            status="compress_error",
            duration_ms=call.elapsed_ms,
            response_kind=response_kind,
            error_message=msg,
            raw_b64=raw_b64,
            image_url=raw_out.image_url,
            decoded_bytes=blob,
        )
        _insert_cover_image_log(
            db,
            project=project,
            provider=provider,
            payload=payload,
            status="compress_error",
            duration_ms=call.elapsed_ms,
            response_kind=response_kind,
            gateway_url=call.gateway_url,
            http_status=call.http_status,
            error_message=msg,
            debug_bundle_rel_path=dbg,
            result_cover_url=None,
        )
        raise HTTPException(502, msg) from e

    _insert_cover_image_log(
        db,
        project=project,
        provider=provider,
        payload=payload,
        status="ok",
        duration_ms=call.elapsed_ms,
        response_kind=response_kind,
        gateway_url=call.gateway_url,
        http_status=call.http_status,
        error_message=None,
        debug_bundle_rel_path=None,
        result_cover_url=path,
    )
    return CoverGenerateOut(cover_url=path)
