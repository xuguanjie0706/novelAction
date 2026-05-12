"""AUTO-GENERATED mixin chunk from legacy ai_service — see package docstring."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import List, AsyncGenerator, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.config import settings
from app.services.llm_config import normalize_openai_base_url, resolve_gemini_connection
from app.services.llm_task_profiles import resolve_task_profile
from app.services.llm_token_budgets import (
    max_tokens_auto_debrief,
    max_tokens_chapter_quality_check,
    max_tokens_coherence_apply,
    max_tokens_coherence_check,
    max_tokens_draft_stream,
    max_tokens_expand_outline,
    max_tokens_extract_memory,
    max_tokens_outline_quality_check,
    max_tokens_plan_full_structure,
    max_tokens_quality_micro_patch,
    max_tokens_suggest_stream,
)
from app.services.llm_call_log import log_llm_call
from app.services.genre_kit import get_genre_guardrail, normalize_genre
from app.services.xuanhuan_lexicon import (
    format_modern_blacklist_for_prompt,
    is_xuanhuan_like_genre,
)
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block


class CoherenceMixin:
    async def chapter_coherence_check(
        self,
        project_title: str,
        chapters: List[dict],
        project_context: str = "",
    ) -> dict:
        """
        对多章进行连贯性检查：
        1) 标题与内容是否匹配
        2) 章节间剧情推进是否连贯
        """
        large_context = self._large_context_enabled()
        chapter_blocks = []
        for idx, chapter in enumerate(chapters, start=1):
            title = chapter.get("title", "未命名章节")
            content = self._plain_text(chapter.get("content") or "")
            narr_c, _ = split_plain_manuscript_and_index_block(content)
            if narr_c.strip():
                content = narr_c.strip()
            content_preview = self._clip_context(content, 1800, 60000) if content else "（正文为空）"
            content_label = "完整正文" if large_context else "正文（截断）"
            chapter_blocks.append(
                f"[样本{idx}] 章节ID={chapter.get('id')} | 顺序={chapter.get('sort_order', idx - 1)}\n"
                f"标题：{title}\n"
                f"{content_label}：\n{content_preview}"
            )
        chapters_text = "\n\n".join(chapter_blocks)
        context_text = (
            f"\n\n项目连续性资料（优先作为判断依据）：\n"
            f"{self._clip_context(project_context, 1200, 30000)}"
            if project_context else ""
        )

        system = """你是资深网文编辑，擅长检查章节标题与剧情的一致性，以及多章连续阅读时的剧情连贯性。
必须严格返回 JSON，不要输出任何解释性文字。"""

        prompt = f"""小说：{project_title}
{context_text}

下面是按章节顺序选出的正文样本，请做连贯性检测：
{chapters_text}

请重点检查：
1. 每章“标题-正文”是否匹配（是否标题党、偏题、内容兑现不足）
2. 章节之间剧情推进是否自然（动机、冲突、信息承接、时间线）
3. 是否存在明显断层（人物状态突变、因果缺失、场景跳跃）

返回 JSON（字段名固定）：
{{
  "title_match_score": 8.2,
  "continuity_score": 7.6,
  "overall_score": 7.9,
  "chapter_evaluations": [
    {{
      "chapter_id": "uuid",
      "chapter_title": "第12章 ...",
      "title_match_score": 8,
      "title_match_comment": "标题与正文主事件基本一致",
      "risk_level": "low"
    }}
  ],
  "cross_chapter_issues": [
    {{
      "type": "continuity_gap",
      "severity": "warning",
      "description": "第12章结尾主角重伤，第13章开头直接满状态出战，缺少恢复或解释"
    }}
  ],
  "suggestions": [
    "按章节顺序给出可执行修改建议"
  ],
  "summary": "一句话总评"
}}

硬性数量要求（在真实问题规模允许的前提下尽量满足，勿用少量笼统条目敷衍）：
- cross_chapter_issues：有明显问题时**至少 6 条**、问题多时可到 **20 条**；不要无故停在 4 条左右。
- suggestions：**至少 8 条、至多 18 条**，逐条具体可执行；按章节顺序组织，覆盖标题兑现、承接、人物状态、时间线、伏笔、节奏与信息密度；禁止把多条合并成一句空话。
- chapter_evaluations：须覆盖**每一章**一条，字段填完整。"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_coherence_check(large_context),
            context={"operation": "chapter_coherence_check"},
            task="quality.coherence_check",
        )
        try:
            import re

            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            return json.loads(text)
        except Exception:
            return {
                "title_match_score": 0,
                "continuity_score": 0,
                "overall_score": 0,
                "chapter_evaluations": [],
                "cross_chapter_issues": [],
                "suggestions": [],
                "summary": "",
                "error": "Failed to parse AI response",
                "raw_response": response,
            }

    def _slim_coherence_for_apply(self, coherence: dict) -> dict:
        keys = (
            "title_match_score",
            "continuity_score",
            "overall_score",
            "chapter_evaluations",
            "cross_chapter_issues",
            "suggestions",
            "summary",
        )
        out = {k: coherence.get(k) for k in keys if k in coherence}
        return out if isinstance(coherence, dict) else {}

    def _parse_coherence_apply_json(self, response: str) -> dict:
        text = (response or "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if "```" in text:
            fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
            if fence:
                text = fence.group(1).strip()
        start = text.find("{")
        if start != -1:
            text = text[start:]
        return json.loads(text)

    def _author_directives_block(
        self,
        focus_keywords: Optional[List[str]],
        revision_note: Optional[str],
    ) -> str:
        parts: List[str] = []
        if focus_keywords:
            kw = [str(k).strip() for k in focus_keywords if str(k).strip()]
            if kw:
                parts.append("【作者关键词侧重】" + "、".join(kw[:40]))
        note = (revision_note or "").strip()
        if note:
            parts.append("【作者补充说明】" + note[:2500])
        if not parts:
            return ""
        return (
            "\n\n"
            + "\n".join(parts)
            + "\n\n约束：若作者说明与上文「连贯性评测结果」中的具体诊断冲突，以评测结论为准；"
            "作者说明仅用于调整优先级、措辞与侧重点。\n"
        )

    async def apply_coherence_revisions(
        self,
        *,
        project_title: str,
        coherence: dict,
        chapters: List[dict],
        focus_keywords: Optional[List[str]] = None,
        revision_note: Optional[str] = None,
    ) -> List[dict]:
        """
        根据连贯性评测结论，对所选章节正文做最小幅度修订（非整章重写）。
        Gemini：一次批量；本地：逐章调用以控制上下文。
        """
        if not chapters:
            return []

        large = self._large_context_enabled()
        slim = self._slim_coherence_for_apply(coherence or {})
        coherence_json = json.dumps(slim, ensure_ascii=False)
        coherence_json = self._clip_context(coherence_json, 10000, 56000)
        author_block = self._author_directives_block(focus_keywords, revision_note)

        system = (
            "你是资深网文编辑，只根据给定的「连贯性评测」结论修订正文。"
            "必须严格返回 JSON，不要输出任何 JSON 以外的文字。"
        )

        if large:
            blocks = []
            for idx, ch in enumerate(chapters, start=1):
                cid = str(ch.get("id", ""))
                title = ch.get("title") or "未命名"
                body = ch.get("content") or ""
                body = self._clip_context(body, 16000, 48000)
                blocks.append(
                    f"### 第{idx}章\n章节ID={cid}\n标题：{title}\n正文：\n{body if body else '（空）'}"
                )
            joined = "\n\n".join(blocks)
            prompt = f"""小说：{project_title}

【连贯性评测结果】（JSON）
{coherence_json}
{author_block}
【待处理章节正文】（按顺序，与评测所选章节一致）
{joined}

任务：
1. 仅针对评测中的跨章问题、章节点评、修改建议做**最小必要**改动；禁止更换主线、禁止整章重写。
2. 未指出的问题一律不动；能不改的句子保持原样（含原有 HTML 标签结构；若原文无标签则保持纯文本）。
3. 输出 JSON，结构如下（chapter_revisions 条数与顺序必须与输入章节一致）：
{{
  "chapter_revisions": [
    {{
      "chapter_id": "与输入完全一致",
      "unchanged": true,
      "revised_content": "",
      "change_note": "未改动"
    }}
  ]
}}
若某章需要修改：unchanged 为 false，revised_content 为该章**完整**修后正文；若无需修改：unchanged 为 true 且 revised_content 为空字符串。"""

            response = await self._call_ai(
                system,
                prompt,
                max_tokens=max_tokens_coherence_apply(True),
                context={"operation": "chapter_coherence_apply"},
                task="quality.coherence_apply",
            )
            try:
                data = self._parse_coherence_apply_json(response)
            except Exception:
                raise ValueError("模型返回的修订 JSON 无法解析") from None
            rows = data.get("chapter_revisions") or data.get("revisions")
            if not isinstance(rows, list):
                raise ValueError("修订结果缺少 chapter_revisions 数组")
            by_id = {str(r.get("chapter_id", "")): r for r in rows if isinstance(r, dict)}
            merged: List[dict] = []
            for ch in chapters:
                cid = str(ch.get("id", ""))
                row = by_id.get(cid) or {}
                unchanged = bool(row.get("unchanged", True))
                revised = (row.get("revised_content") or "").strip()
                if not unchanged and not revised:
                    unchanged = True
                note = str(row.get("change_note") or "").strip()[:200]
                orig = ch.get("content") or ""
                if unchanged or not revised:
                    merged.append(
                        {
                            "chapter_id": cid,
                            "unchanged": True,
                            "revised_content": "",
                            "change_note": note or "未改动",
                        }
                    )
                else:
                    merged.append(
                        {
                            "chapter_id": cid,
                            "unchanged": False,
                            "revised_content": revised,
                            "change_note": note or "已修订",
                        }
                    )
            return merged

        merged_seq: List[dict] = []
        for i, ch in enumerate(chapters):
            cid = str(ch.get("id", ""))
            title = ch.get("title") or "未命名"
            body = ch.get("content") or ""
            prev_plain = self._plain_text(chapters[i - 1].get("content")) if i > 0 else ""
            next_plain = self._plain_text(chapters[i + 1].get("content")) if i + 1 < len(chapters) else ""
            prev_tail = self._clip_context(prev_plain[-1200:], 1200, 1200, from_end=True) if prev_plain else ""
            next_head = self._clip_context(next_plain[:800], 800, 800) if next_plain else ""

            prompt = f"""小说：{project_title}

【连贯性评测结果】（JSON）
{coherence_json}
{author_block}
【相邻上下文（纯文本摘录，仅供衔接判断）】
上一章结尾：{prev_tail or "（无）"}
下一章开头：{next_head or "（无）"}

【当前待修订章节】
章节ID：{cid}
标题：{title}
正文（请保持原有 HTML/标签结构；若无标签则保持纯文本）：
{self._clip_context(body, 10000, 22000)}

任务：只根据评测结论修订**本章节**；禁止整章重写；未涉及处保持原文。
返回 JSON：
{{
  "chapter_id": "{cid}",
  "unchanged": true,
  "revised_content": "",
  "change_note": "未改动"
}}
若需修改：unchanged=false，revised_content 填完整修后正文；否则 unchanged=true 且 revised_content 为空。"""

            response = await self._call_ai(
                system,
                prompt,
                max_tokens=max_tokens_coherence_apply(False),
                context={"operation": "chapter_coherence_apply"},
                task="quality.coherence_apply",
            )
            try:
                row = self._parse_coherence_apply_json(response)
            except Exception:
                raise ValueError(f"第 {i + 1} 章修订 JSON 无法解析") from None
            if str(row.get("chapter_id", "")) != cid:
                row["chapter_id"] = cid
            unchanged = bool(row.get("unchanged", True))
            revised = (row.get("revised_content") or "").strip()
            if not unchanged and not revised:
                unchanged = True
            note = str(row.get("change_note") or "").strip()[:200]
            merged_seq.append(
                {
                    "chapter_id": cid,
                    "unchanged": unchanged or not revised,
                    "revised_content": "" if unchanged or not revised else revised,
                    "change_note": note or ("未改动" if unchanged else "已修订"),
                }
            )
        return merged_seq

    # ── 流式建议 ──────────────────────────────────────
