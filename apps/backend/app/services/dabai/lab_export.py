"""dabai 实验书架 — 正文 / 章纲 / 投稿包导出。

大白文正文为纯文本（非 HTML），与精品文 export_service 隔离，复用章节标题格式化与平台规则。
"""
from __future__ import annotations

import io
import re
import zipfile

from app.models.dabai import DabaiChapterOutline, DabaiProject, DabaiVolume
from app.services.export_service import (
    PLATFORM_RULES,
    ChapterIssue,
    ExportPreview,
    build_chapter_header,
)


def _word_count(ch: DabaiChapterOutline) -> int:
    return len((ch.content or "").strip())


def dabai_chapter_to_plain(ch: DabaiChapterOutline) -> str:
    """章纯正文 → 投稿用纯文本（压缩多余空行）。"""
    body = (ch.content or "").strip()
    if not body:
        return ""
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _group_by_volume(
    volumes: list[DabaiVolume],
    chapters: list[DabaiChapterOutline],
) -> list[tuple[DabaiVolume, list[DabaiChapterOutline]]]:
    vols = sorted(volumes, key=lambda v: v.volume_number or 0)
    chs = sorted(chapters, key=lambda c: c.chapter_number or 0)
    start = 1
    groups: list[tuple[DabaiVolume, list[DabaiChapterOutline]]] = []
    for vol in vols:
        planned = max(vol.planned_chapters or 1, 1)
        end = start + planned - 1
        slice_chs = [c for c in chs if start <= (c.chapter_number or 0) <= end]
        groups.append((vol, slice_chs))
        start = end + 1
    return groups


def build_dabai_txt(project: DabaiProject, chapters: list[DabaiChapterOutline]) -> str:
    """全书 TXT：书名 + 简介 + 各章标题与正文。"""
    lines: list[str] = [
        project.title or "未命名",
    ]
    pos = project.positioning or {}
    genre = pos.get("genre") or pos.get("pace_type")
    if genre:
        lines.append(f"题材：{genre}")
    if project.logline:
        lines.append(f"简介：{project.logline}")
    lines.extend(["=" * 40, ""])

    exported = 0
    for ch in sorted(chapters, key=lambda c: c.chapter_number or 0):
        body = dabai_chapter_to_plain(ch)
        if not body:
            continue
        n = ch.chapter_number or (exported + 1)
        lines.append(build_chapter_header(n, ch.title or ""))
        lines.extend(["", body, "", ""])
        exported += 1

    if exported == 0:
        lines.append("（暂无已完成章节）")

    return "\n".join(lines)


def build_dabai_zip(project: DabaiProject, chapters: list[DabaiChapterOutline]) -> bytes:
    """ZIP 投稿包：manifest + 全文 + 分章文件。"""
    buf = io.BytesIO()
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", project.title or "novel")
    full_txt = build_dabai_txt(project, chapters)
    written = [c for c in chapters if _word_count(c) > 0]
    total_words = sum(_word_count(c) for c in written)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = "\n".join([
            f"书名：{project.title or '未命名'}",
            f"总字数：{total_words:,}",
            f"章节数：{len(written)}",
            f"简介：{project.logline or '未设置'}",
        ])
        zf.writestr(f"{safe_title}/manifest.txt", manifest.encode("utf-8"))
        zf.writestr(f"{safe_title}/full_manuscript.txt", full_txt.encode("utf-8"))

        seq = 1
        for ch in sorted(chapters, key=lambda c: c.chapter_number or 0):
            body = dabai_chapter_to_plain(ch)
            if not body:
                continue
            n = ch.chapter_number or seq
            header = build_chapter_header(n, ch.title or "")
            safe_ch = re.sub(r'[\\/:*?"<>|]', "_", ch.title or f"chapter_{seq}")
            zf.writestr(
                f"{safe_title}/chapters/{seq:03d}_{safe_ch}.txt",
                f"{header}\n\n{body}".encode("utf-8"),
            )
            seq += 1

    return buf.getvalue()


def _chapter_outline_lines(ch: DabaiChapterOutline, indent: str) -> list[str]:
    n = ch.chapter_number or 0
    title = (ch.title or "").strip() or f"第{n}章"
    lines = [f"{indent}## 第{n}章 {title}"]
    fields: list[tuple[str, str | None]] = [
        ("爽点类型", ch.shuang_type),
        ("场景", ch.location),
        ("憋屈", ch.yaqu_setup),
        ("转折", ch.emotion_turn),
        ("引爆", ch.yinbao),
        ("爽感", ch.shuang_payoff),
        ("钩子", ch.end_hook),
    ]
    for label, val in fields:
        text = (val or "").strip()
        if text:
            lines.append(f"{indent}  - {label}：{text}")
    witnesses = ch.witnesses or []
    if witnesses:
        names = ", ".join(str(w) for w in witnesses if w)
        if names:
            lines.append(f"{indent}  - 见证者：{names}")
    return lines


def build_dabai_outline_txt(
    project: DabaiProject,
    volumes: list[DabaiVolume],
    chapters: list[DabaiChapterOutline],
) -> str:
    """章纲大纲 TXT：卷 → 章 + 五拍字段。"""
    lines: list[str] = [
        f"《{project.title or '未命名'}》章纲大纲",
    ]
    if project.logline:
        lines.append(f"简介：{project.logline}")
    lines.extend(["=" * 40, ""])

    groups = _group_by_volume(volumes, chapters)
    if not groups and chapters:
        for ch in sorted(chapters, key=lambda c: c.chapter_number or 0):
            lines.extend(_chapter_outline_lines(ch, ""))
            lines.append("")
    else:
        for vol, vol_chs in groups:
            vn = vol.volume_number or 0
            vt = (vol.title or "").strip()
            lines.append(f"# 第{vn}卷 {vt}".rstrip())
            if vol.volume_climax:
                lines.append(f"  - 卷末高潮：{vol.volume_climax.strip()}")
            lines.append("")
            for ch in vol_chs:
                lines.extend(_chapter_outline_lines(ch, "  "))
                lines.append("")

    if len(lines) <= 4:
        lines.append("（暂无章纲内容）")

    return "\n".join(lines).rstrip() + "\n"


def check_dabai_compliance(
    chapters: list[DabaiChapterOutline],
    platform: str = "general",
) -> ExportPreview:
    """对照平台字数规则检查 dabai 章节（纯 DB，无 AI）。"""
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["general"])
    min_w: int = rules["min_words"]
    max_w: int = rules["max_words"]

    issues: list[ChapterIssue] = []
    compliant = 0
    total_words = 0
    sorted_chs = sorted(chapters, key=lambda c: c.chapter_number or 0)

    for i, ch in enumerate(sorted_chs, start=1):
        wc = _word_count(ch)
        total_words += wc
        n = ch.chapter_number or i
        title = ch.title or f"第{n}章"

        if wc == 0:
            status, msg = "empty", "章节无正文，将在导出时跳过"
        elif min_w > 0 and wc < min_w:
            status = "too_short"
            msg = f"{wc} 字，低于 {rules['name']} 最低要求 {min_w} 字"
        elif wc > max_w:
            status = "too_long"
            msg = f"{wc} 字，超过 {rules['name']} 上限 {max_w} 字"
        else:
            status = "ok"
            msg = ""
            compliant += 1

        if status != "ok":
            issues.append(ChapterIssue(
                chapter_id=str(ch.id),
                title=title,
                sort_order=n,
                word_count=wc,
                status=status,
                message=msg,
            ))

    return ExportPreview(
        total_chapters=len(sorted_chs),
        total_words=total_words,
        platform=platform,
        platform_name=rules["name"],
        compliant_chapters=compliant,
        issues=issues,
    )


def chapters_with_content(chapters: list[DabaiChapterOutline]) -> list[DabaiChapterOutline]:
    """仅保留有正文的章节，按章号排序。"""
    return sorted(
        [c for c in chapters if _word_count(c) > 0],
        key=lambda c: c.chapter_number or 0,
    )
