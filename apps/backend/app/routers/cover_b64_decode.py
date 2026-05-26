"""
cover_b64_decode.py — 封面图片 base64 解码与纠错

从网关返回的多种脏 base64 payload 中恢复出可用的图片字节流。
覆盖场景：data URL 剥层、JSON 嵌套字段、扩展 base64 变体、urlsafe、hex、
二次 base64 文本链、gzip/zlib、二进制内嵌扫描，最后用 PIL 验证。

本模块为纯函数模块，不依赖 FastAPI / SQLAlchemy / httpx，仅做字节级解码。
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from io import BytesIO
from typing import Iterable, List, Optional

from PIL import Image


# ── base64 规范化 ────────────────────────────────────────────────

def normalize_b64_json_from_provider(raw: Optional[str]) -> str:
    """
    部分网关/代理商在 b64_json 里直接塞完整 data URL，或带首尾引号；
    若再包一层 data:image/png;base64,... 会导致逗号后不是纯 base64。此处剥到最内层 payload。
    """
    if raw is None:
        return ""
    s = "".join(str(raw).split()).strip("﻿​‌‍")
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


# ── 魔数识别 ────────────────────────────────────────────────────

def image_magic_kind(blob: bytes) -> Optional[str]:
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


# ── base64 变体生成 ─────────────────────────────────────────────

def _base64_input_variants_extended(raw: str) -> List[str]:
    """
    尽可能覆盖网关脏数据：去空白、去多余 =、mod4 修边、首尾少量非字母数字垃圾。
    """
    s0 = "".join((raw or "").split()).strip("﻿​‌‍")
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


# ── JSON 嵌套提取 ───────────────────────────────────────────────

def _extract_json_strings_for_image(obj: object, acc: List[str], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(obj, str):
        if len(obj) > 80:
            acc.append(obj)
        return
    if isinstance(obj, dict):
        priority_keys = (
            "b64_json", "image", "image_base64", "base64",
            "data", "content", "result", "bytes", "file",
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


# ── 解压 / 切片 ─────────────────────────────────────────────────

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
        b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n",
        b"GIF87a", b"GIF89a", b"RIFF", b"BM",
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


# ── 多层剥开 / 候选展开 ─────────────────────────────────────────

def _strings_for_decode_from_raw(raw: str) -> List[str]:
    raw = normalize_b64_json_from_provider(raw)
    acc: List[str] = [raw]
    acc.extend(_try_json_wrapped_payload(raw))
    seen: set[str] = set()
    out: List[str] = []
    for s in acc:
        c = normalize_b64_json_from_provider(s)
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
        if image_magic_kind(cur):
            break
        txt: Optional[str] = None
        try:
            txt = cur.decode("utf-8")
        except Exception:
            try:
                txt = cur.decode("latin-1")
            except Exception:
                break
        nxt_str = normalize_b64_json_from_provider(txt.strip())
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


# ── 主入口 ──────────────────────────────────────────────────────

def decode_b64_image_payload(raw: str) -> bytes:
    """
    多路径兜底解码 base64 图片 payload，返回可被 PIL 打开的原始字节。

    Raises:
        ValueError: 所有解码路径均失败时。
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
        if image_magic_kind(blob):
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
