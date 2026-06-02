"""
导出服务：TXT 纯文本 / ZIP 投稿包生成 / 平台合规预检。

设计原则：
- PLATFORM_RULES 驱动：新增平台只追加配置，不改核心逻辑。
- 纯函数为主：所有格式化函数无副作用，便于单元测试。
- 违禁词扫描由 AI 负责（services/ai/violation_check.py），本模块只做结构性校验。
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from app.models import Chapter, OutlineNode, Project
from app.utils.chapter_manuscript import (
    html_to_plain_for_revision,
    split_plain_manuscript_and_index_block,
)
from app.routers.ai.text_utils import strip_tail_meta_lines

# ── 平台规则配置 ──────────────────────────────────────────────────────────────
# 新增平台：在此追加 key，不需修改任何其他函数。

PLATFORM_RULES: dict[str, dict] = {
    "qidian": {
        "name": "起点中文网",
        "min_words": 1500,
        "max_words": 6000,
    },
    "jjwxc": {
        "name": "晋江文学城",
        "min_words": 1000,
        "max_words": 10000,
    },
    "fanqie": {
        "name": "番茄小说",
        "min_words": 1200,
        "max_words": 5000,
    },
    "general": {
        "name": "通用",
        "min_words": 0,
        "max_words": 999_999,
    },
}


@dataclass
class ChapterIssue:
    """单章合规问题记录。"""
    chapter_id: str
    title: str
    sort_order: int
    word_count: int
    status: str          # ok | too_short | too_long | empty
    message: str = ""


@dataclass
class ExportPreview:
    """导出预览：合规统计 + 问题章节列表。"""
    total_chapters: int
    total_words: int
    platform: str
    platform_name: str
    compliant_chapters: int
    issues: list[ChapterIssue] = field(default_factory=list)


# ── 纯文本清洗 ────────────────────────────────────────────────────────────────

def chapter_to_plain(chapter: Chapter) -> str:
    """
    将章节 HTML 正文转换为投稿用纯文本。

    处理流程：
      HTML 解析 → 去稿末 ch_ 索引块 → 去章末质检元信息行 → 清理多余空行。

    Args:
        chapter: Chapter ORM 实例，读取 content 字段。

    Returns:
        纯文本正文，段落间双换行，首行不含章节标题（标题由调用方单独处理）。
        若章节无内容则返回空字符串。
    """
    raw_html = chapter.content or ""
    if not raw_html.strip():
        return ""

    # 1. HTML → 有段落换行的纯文本（与前端 htmlToPlainForSplit 对齐）
    plain = html_to_plain_for_revision(raw_html)

    # 2. 分离稿末 ### ch_ 索引块，只保留叙事正文
    body, _ = split_plain_manuscript_and_index_block(plain)

    # 3. 去掉 AI 写章时生成的章末元信息行（钩子强度、伏笔标记等）
    body = strip_tail_meta_lines(body)

    # 4. 压缩多余空行（≥3 个换行 → 2 个），保留段落分隔
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return body


def build_chapter_header(n: int, title: str) -> str:
    """
    生成标准章节标题行。

    去掉原标题中已有的「第X章」前缀，重新以序号格式化，
    避免出现「第1章 第1章 烽火」这样的重复。

    Args:
        n: 导出序号（从 1 开始）。
        title: 章节原始标题。

    Returns:
        形如「第1章 烽火连城」的标题行。
    """
    clean = re.sub(r"^第\s*\d+\s*章\s*", "", title or "").strip()
    return f"第{n}章 {clean}" if clean else f"第{n}章"


# ── 格式构建 ──────────────────────────────────────────────────────────────────

def build_txt(project: Project, chapters: list[Chapter]) -> str:
    """
    生成全书 TXT 纯文本（可直接复制粘贴至平台编辑器）。

    格式：书名 → 题材/简介 → 分隔线 → 各章（标题 + 空行 + 正文 + 双空行）。
    空章节（无正文）自动跳过，不占位。

    Args:
        project: 项目实例，提供书名/题材/梗概元信息。
        chapters: 已按 sort_order 排序的章节列表。

    Returns:
        UTF-8 字符串，可直接写文件或作为 HTTP 下载响应体。
    """
    lines: list[str] = []

    # ── 书头 ──
    lines.append(project.title or "未命名")
    if project.genre:
        lines.append(f"题材：{project.genre}")
    if project.logline:
        lines.append(f"简介：{project.logline}")
    lines.append("=" * 40)
    lines.append("")

    exported = 0
    for i, ch in enumerate(chapters, start=1):
        body = chapter_to_plain(ch)
        if not body:
            continue
        lines.append(build_chapter_header(i, ch.title or ""))
        lines.append("")
        lines.append(body)
        lines.append("")
        lines.append("")
        exported += 1

    if exported == 0:
        lines.append("（暂无已完成章节）")

    return "\n".join(lines)


def build_zip_package(project: Project, chapters: list[Chapter]) -> bytes:
    """
    生成投稿包 ZIP，包含全文稿、分章文件及清单。

    ZIP 结构：
        {书名}/
            manifest.txt           # 元信息（书名/题材/字数/章数/简介）
            full_manuscript.txt    # 完整正文（平台直接粘贴用）
            chapters/
                001_章节名.txt
                002_章节名.txt
                ...

    Args:
        project: 项目实例。
        chapters: 已排序章节列表（空章节自动跳过）。

    Returns:
        ZIP 文件字节流，可直接作为 FastAPI FileResponse / Response body 下载。
    """
    buf = io.BytesIO()
    # 去掉文件名中的特殊字符，保证跨平台兼容
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", project.title or "novel")

    full_txt = build_txt(project, chapters)
    total_words = sum(ch.word_count or 0 for ch in chapters if (ch.word_count or 0) > 0)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # manifest.txt
        manifest_lines = [
            f"书名：{project.title or '未命名'}",
            f"题材：{project.genre or '未设置'}",
            f"总字数：{total_words:,}",
            f"章节数：{len([c for c in chapters if (c.word_count or 0) > 0])}",
            f"简介：{project.logline or '未设置'}",
        ]
        zf.writestr(
            f"{safe_title}/manifest.txt",
            "\n".join(manifest_lines).encode("utf-8"),
        )

        # full_manuscript.txt
        zf.writestr(
            f"{safe_title}/full_manuscript.txt",
            full_txt.encode("utf-8"),
        )

        # 分章文件
        seq = 1
        for ch in chapters:
            body = chapter_to_plain(ch)
            if not body:
                continue
            header = build_chapter_header(seq, ch.title or "")
            ch_content = f"{header}\n\n{body}"
            safe_ch = re.sub(r'[\\/:*?"<>|]', "_", ch.title or f"chapter_{seq}")
            fname = f"{seq:03d}_{safe_ch}.txt"
            zf.writestr(
                f"{safe_title}/chapters/{fname}",
                ch_content.encode("utf-8"),
            )
            seq += 1

    return buf.getvalue()


# ── 大纲导出 ──────────────────────────────────────────────────────────────────

# 节点类型 → 中文标签（用于无标题节点的兜底前缀）
_NODE_TYPE_LABEL: dict[str, str] = {
    "volume": "卷",
    "arc": "篇章",
    "chapter_plan": "章节",
}


def _outline_node_block(node: OutlineNode, depth: int) -> list[str]:
    """
    将单个大纲节点渲染为若干文本行（不含子节点）。

    按层级缩进，标题前用 Markdown 风格的 # 标记层级，
    随后按存在与否追加摘要 / 钩子 / 燃点 / 冲突 / 实力里程碑等字段。

    Args:
        node: 大纲节点 ORM 实例。
        depth: 当前层级深度（0=卷），决定标题井号数量与正文缩进。

    Returns:
        文本行列表。
    """
    lines: list[str] = []
    label = _NODE_TYPE_LABEL.get(node.node_type or "", "")
    title = (node.title or "").strip() or (label or "未命名")
    heading = "#" * min(depth + 1, 6)
    lines.append(f"{heading} {title}")

    indent = "    " * depth
    fields: list[tuple[str, str | None]] = [
        ("摘要", node.summary),
        ("冲突", node.conflict),
        ("钩子", node.hook),
        ("燃点", node.highlight),
        ("实力里程碑", node.power_milestone),
    ]
    for fname, val in fields:
        text = (val or "").strip() if val else ""
        if text:
            lines.append(f"{indent}- {fname}：{text}")
    return lines


def build_outline_txt(project: Project, nodes: list[OutlineNode]) -> str:
    """
    生成全书大纲文本（Markdown 风格，树形缩进）。

    从扁平节点列表按 parent_id 重建树，按 sort_order 排序，
    自上而下输出 卷 → 篇章 → 章节计划 的层级结构及各节点字段。

    Args:
        project: 项目实例，提供书名/题材/简介。
        nodes: 项目全部大纲节点（任意顺序）。

    Returns:
        UTF-8 字符串，可直接写文件或作为下载响应体。
    """
    lines: list[str] = []

    # ── 书头 ──
    lines.append(f"《{project.title or '未命名'}》大纲")
    if project.genre:
        lines.append(f"题材：{project.genre}")
    if project.logline:
        lines.append(f"简介：{project.logline}")
    lines.append("=" * 40)
    lines.append("")

    # ── 重建树 ──
    children_map: dict[str | None, list[OutlineNode]] = {}
    for n in nodes:
        pid = str(n.parent_id) if n.parent_id else None
        children_map.setdefault(pid, []).append(n)
    for bucket in children_map.values():
        bucket.sort(key=lambda x: (x.sort_order or 0))

    def walk(parent_key: str | None, depth: int) -> None:
        for node in children_map.get(parent_key, []):
            lines.extend(_outline_node_block(node, depth))
            lines.append("")
            walk(str(node.id), depth + 1)

    walk(None, 0)

    if len(lines) <= 5:
        lines.append("（暂无大纲内容）")

    return "\n".join(lines).rstrip() + "\n"


# ── 合规预检 ──────────────────────────────────────────────────────────────────

def check_compliance(
    chapters: list[Chapter],
    platform: str = "general",
) -> ExportPreview:
    """
    对照平台字数规则检查所有章节合规性，返回预览统计。

    不涉及 AI 调用，纯 DB 数据，毫秒级响应。

    Args:
        chapters: 待导出章节列表（已排序）。
        platform: 平台 key，需在 PLATFORM_RULES 中注册；未知 key 降级为 general。

    Returns:
        ExportPreview 含总字数、合规章节数、问题章节明细列表。
    """
    rules = PLATFORM_RULES.get(platform, PLATFORM_RULES["general"])
    min_w: int = rules["min_words"]
    max_w: int = rules["max_words"]

    issues: list[ChapterIssue] = []
    compliant = 0
    total_words = 0

    for i, ch in enumerate(chapters, start=1):
        wc = ch.word_count or 0
        total_words += wc

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
                title=ch.title or f"第{i}章",
                sort_order=i,
                word_count=wc,
                status=status,
                message=msg,
            ))

    return ExportPreview(
        total_chapters=len(chapters),
        total_words=total_words,
        platform=platform,
        platform_name=rules["name"],
        compliant_chapters=compliant,
        issues=issues,
    )
