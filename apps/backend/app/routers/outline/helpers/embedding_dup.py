"""基于 embedding 的章节大纲软重复检测。"""
from __future__ import annotations

from app.routers.outline.helpers.severity import _HARD_RULE_SEVERITY_TO_SCORE
from app.routers.outline.helpers.text_utils import _clean_outline_text

# 把每章压成一段文本喂给 embedding，再做余弦比较。
# 余弦阈值参考：
#   ≥ 0.92 → 几乎确定重复（critical）
#   ≥ 0.85 → 高度相似软重复（high）
#   ≥ 0.78 → 怀疑同质化（medium）
SEMANTIC_DUP_THRESHOLD_HIGH = 0.85
SEMANTIC_DUP_THRESHOLD_MEDIUM = 0.78
SEMANTIC_DUP_WINDOW_VOLUME = 9999      # volume 范围内全配对
SEMANTIC_DUP_WINDOW_BOOK = 60          # book 范围内只比相邻 60 章


def _outline_chapter_signature_text(chapter: dict) -> str:
    parts: list[str] = []
    for field in ("title", "core_event", "character_change", "end_hook"):
        text = _clean_outline_text(chapter.get(field), 220)
        if text:
            parts.append(text)
    return " || ".join(parts)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a ** 0.5 * norm_b ** 0.5)


def _detect_outline_embedding_duplicates(
    chapters: list[dict],
    vectors_by_number: dict[int, list[float]],
    *,
    scope: str = "volume",
    threshold_high: float = SEMANTIC_DUP_THRESHOLD_HIGH,
    threshold_medium: float = SEMANTIC_DUP_THRESHOLD_MEDIUM,
) -> list[dict]:
    """
    纯函数：对已经向量化好的章节做两两余弦比较，超过阈值视为软重复。
      - cosine ≥ threshold_high → high 严重度（追读节奏受损）。
      - cosine ≥ threshold_medium → medium 严重度（提示同质化）。
    跨距过远的对（在 book 范围下 > SEMANTIC_DUP_WINDOW_BOOK）不参与比较。
    """
    if not chapters or len(vectors_by_number) < 2:
        return []
    sorted_chapters = sorted(
        [c for c in chapters if isinstance(c.get("number"), int) and c["number"] in vectors_by_number],
        key=lambda c: c["number"],
    )
    if len(sorted_chapters) < 2:
        return []

    window = SEMANTIC_DUP_WINDOW_VOLUME if scope == "volume" else SEMANTIC_DUP_WINDOW_BOOK

    issues: list[dict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, ch_a in enumerate(sorted_chapters):
        n_a = ch_a["number"]
        v_a = vectors_by_number[n_a]
        for ch_b in sorted_chapters[i + 1:]:
            n_b = ch_b["number"]
            if n_b - n_a > window:
                break
            pair = (n_a, n_b)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            v_b = vectors_by_number[n_b]
            sim = _cosine_similarity(v_a, v_b)
            if sim >= threshold_high:
                severity = "high"
            elif sim >= threshold_medium:
                severity = "medium"
            else:
                continue
            label_a = _clean_outline_text(ch_a.get("title"), 32) or f"第{n_a}章"
            label_b = _clean_outline_text(ch_b.get("title"), 32) or f"第{n_b}章"
            issues.append({
                "severity": severity,
                "type": "duplicate_event",
                "chapter_numbers": [n_a, n_b],
                "description": (
                    f"第{n_a}章《{label_a}》与第{n_b}章《{label_b}》语义相似度 {sim:.2f}，"
                    "两章在核心事件、人物变化和章末钩子上高度同质，会让读者产生"
                    "「重复看了一遍」的疲劳感。建议拆解为「阶段性失败 → 卷末高潮」"
                    "的递进结构，避免同一目标被反复完成。"
                ),
                "suggested_patch": {
                    "chapter_number": n_b,
                    "field": "core_event",
                    "replacement": "",
                },
            })

    return issues


async def compute_outline_chapter_vectors(
    chapters: list[dict],
) -> dict[int, list[float]]:
    """
    异步：对每个章节签名文本调 embedding_service.embed_texts 拿向量。
    任何失败都安全降级返回空 dict（不影响 QC 主流程）。
    """
    from app.services.embedding_service import embed_texts

    pairs: list[tuple[int, str]] = []
    for chapter in chapters:
        number = chapter.get("number")
        if not isinstance(number, int):
            continue
        text = _outline_chapter_signature_text(chapter)
        if not text:
            continue
        pairs.append((number, text))
    if len(pairs) < 2:
        return {}
    try:
        vectors = await embed_texts([text for _, text in pairs])
    except Exception:
        return {}
    if not vectors or len(vectors) != len(pairs):
        return {}
    return {number: vec for (number, _), vec in zip(pairs, vectors) if isinstance(vec, list)}


async def analyze_outline_embedding_duplicates(
    chapters: list[dict],
    *,
    scope: str = "volume",
) -> dict:
    """
    异步包装：取向量 → 比对 → 返回与 _detect_outline_hard_rule_issues 同结构的报告。
    embedding 不可用或失败时返回 pass 报告，不阻塞 QC。
    """
    vectors = await compute_outline_chapter_vectors(chapters)
    if not vectors:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "embedding 语义去重未运行（向量服务不可用或样本不足）。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }
    issues = _detect_outline_embedding_duplicates(chapters, vectors, scope=scope)
    if not issues:
        return {
            "overall_score": 100,
            "status": "pass",
            "summary": "embedding 语义去重未发现软重复。",
            "issues": [],
            "must_fix_chapter_numbers": [],
        }
    must_fix = sorted({
        n for issue in issues for n in issue.get("chapter_numbers", []) if isinstance(n, int)
    })
    score = min(_HARD_RULE_SEVERITY_TO_SCORE.get(i.get("severity", ""), 80) for i in issues)
    return {
        "overall_score": score,
        "status": "fail",
        "summary": f"embedding 语义去重发现 {len(issues)} 对软重复章节。",
        "issues": issues,
        "must_fix_chapter_numbers": must_fix,
    }
