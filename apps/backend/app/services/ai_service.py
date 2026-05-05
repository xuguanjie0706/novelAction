"""
AI Service — 统一使用 OpenAI 兼容协议
支持任意 base_url + api_key（含本地 Ollama、自建网关、云厂商兼容端点等）
"""
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
    max_tokens_suggest_stream,
)
from app.services.llm_call_log import log_llm_call
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block


class AIService:
    def __init__(
        self,
        profile: str = "default",
        db: Optional[Session] = None,
        llm_provider_id: Optional[UUID] = None,
    ):
        self.profile = profile
        self._db = db
        self.model = (settings.AI_MODEL or "").strip()
        self.base_url = settings.LLM_BASE_URL
        self.api_key = settings.LLM_API_KEY
        self._gemini_unconfigured = False
        if profile == "gemini":
            conn = resolve_gemini_connection(db, llm_provider_id)
            if conn:
                self.base_url = normalize_openai_base_url(conn[0])
                self.model = conn[1]
                self.api_key = (conn[2] or "").strip() or "not-required"
            else:
                self._gemini_unconfigured = True
        self._client = None
        self._truncation_warnings: list[str] = []  # 本次调用中发生的截断记录

    def _large_context_enabled(self) -> bool:
        return self.profile == "gemini"

    def _clip_context(
        self,
        text: str | None,
        local_limit: int,
        large_limit: int | None,
        from_end: bool = False,
        field_name: str = "",
    ) -> str:
        """裁剪上下文。large_limit=None 表示大上下文模型（Gemini）不截断。
        真正发生截断时记录 warning，并在 self._truncation_warnings 追加提示。
        """
        clean = (text or "").strip()
        if not clean:
            return ""
        if self._large_context_enabled():
            if large_limit is None:
                return clean  # Gemini：不截断
            limit = large_limit
        else:
            limit = local_limit
        if len(clean) <= limit:
            return clean
        label = f"[{field_name}] " if field_name else ""
        logger.warning(
            "⚠️ 上下文截断 %sprofile=%s limit=%d original_len=%d",
            label, self.profile, limit, len(clean),
        )
        self._truncation_warnings.append(
            f"字段 {field_name or '未知'} 被截断：原始长度 {len(clean)} 字符，限制 {limit} 字符"
        )
        return clean[-limit:] if from_end else clean[:limit]

    def _plain_text(self, content: str | None) -> str:
        return re.sub(r"<[^>]+>", "", content or "").strip()

    def _get_client(self):
        """
        始终使用 AsyncOpenAI，通过 base_url + api_key 指向任意 OpenAI 兼容服务（由 profile 与配置决定，无固定厂商）
        """
        if self._gemini_unconfigured:
            raise RuntimeError(
                "未配置远程大模型：请在管理后台「大模型」中新增并启用/设为默认，"
                "或设置环境变量 GEMINI_BASE_URL 与 GEMINI_MODEL"
            )
        if self.profile == "default" and not (self.model or "").strip():
            raise RuntimeError(
                "未配置本地模型：请在 apps/backend/.env 设置 AI_MODEL（OpenAI 兼容的模型 id），"
                "或在前端顶部「模型 / 线路」中选择已启用的远程线路。"
            )
        if self._client:
            return self._client
        import httpx
        import openai

        timeout = httpx.Timeout(
            connect=settings.LLM_HTTP_CONNECT_TIMEOUT,
            read=settings.LLM_HTTP_READ_TIMEOUT,
            write=120.0,
            pool=30.0,
        )
        self._client = openai.AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
        )
        return self._client

    # ── 质检 ──────────────────────────────────────────
    async def quality_check(
        self,
        chapter_content: str,
        chapter_title: str,
        memories: List[str],
        settings_summary: List[str],
        check_types: List[str],
        # 新增：人物当前状态、故事线、大纲节点上下文
        character_states: List[str] = None,
        storylines_context: List[str] = None,
        power_systems_summary: List[str] = None,
        outline_context: str = "",
        continuity_context: str = "",
        chapter_index_context: str = "",
        plot_dossier_context: str = "",
    ) -> dict:
        large_context = self._large_context_enabled()
        memory_count = 120 if large_context else 20
        setting_count = 80 if large_context else 8
        character_count = 80 if large_context else 10
        storyline_count = 40 if large_context else 5
        power_count = 20 if large_context else 5

        memory_text = (
            "\n".join(
                f"- {self._clip_context(m, 180, 1600)}"
                for m in memories[:memory_count]
            )
            if memories else "暂无记忆条目"
        )
        settings_text = (
            "\n".join(
                f"- {self._clip_context(s, 220, 2400)}"
                for s in settings_summary[:setting_count]
            )
            if settings_summary else "暂无设定"
        )

        # 人物当前状态（用于一致性检查的核心）
        char_state_text = ""
        if character_states:
            char_state_text = "\n人物当前状态（一致性检查关键依据）：\n"
            char_state_text += "\n".join(f"- {c}" for c in character_states[:character_count])

        # 故事线进展
        storyline_text = ""
        if storylines_context:
            storyline_text = "\n当前活跃故事线：\n"
            storyline_text += "\n".join(f"- {s}" for s in storylines_context[:storyline_count])

        power_text = ""
        if power_systems_summary:
            power_text = "\n力量体系与境界规则：\n"
            power_text += "\n".join(f"- {s}" for s in power_systems_summary[:power_count])

        # 本章大纲计划
        outline_text = f"\n本章大纲计划：{outline_context}" if outline_context else ""
        continuity_text = (
            f"\n连续性账本（必须据此检查前后承接）：\n"
            f"{self._clip_context(continuity_context, 1200, 20000)}"
            if continuity_context else ""
        )
        chapter_index_text = (
            f"\n章节速查索引（最近章节与未回收伏笔）：\n"
            f"{self._clip_context(chapter_index_context, 1600, 20000)}"
            if chapter_index_context else ""
        )
        plot_dossier_text = (
            f"\n情节档案（章节索引/伏笔/故事线，优先用于一致性核验）：\n"
            f"{self._clip_context(plot_dossier_context, 2200, 30000)}"
            if plot_dossier_context else ""
        )
        chapter_plain = self._plain_text(chapter_content)
        narr_qc, _ = split_plain_manuscript_and_index_block(chapter_plain)
        if narr_qc.strip():
            chapter_plain = narr_qc.strip()
        chapter_body = self._clip_context(chapter_plain, 2000, 120000)
        chapter_label = "完整正文" if large_context else "正文（前2000字）"

        system = """你是专业的网络小说编辑，负责对章节内容进行质量检查。
请严格按照 JSON 格式返回结果，不要有任何额外文字。

特别关注以下一致性问题：
1. 人物使用了超出其当前境界的技能/能力
2. 人物出现在与记录不符的位置
3. 已死亡/封印的人物突然出现
4. 人物行为违背其价值观和动机
5. 使用了尚未习得的技能或尚未获得的道具"""

        prompt = f"""请对以下章节进行质检，返回 JSON 格式。

章节标题：{chapter_title}
章节{chapter_label}：
{chapter_body}
{char_state_text}
{storyline_text}
{power_text}
{outline_text}
{continuity_text}
{chapter_index_text}
{plot_dossier_text}

近期记忆条目（供参考）：
{memory_text}

世界观设定：
{settings_text}

检查维度：{", ".join(check_types)}

返回格式（字段名固定）：
{{
  "overall_score": 8.5,
  "dimensions": {{
    "plot": {{"score": 9, "status": "pass", "comment": "情节推进是否有效"}},
    "character": {{"score": 8, "status": "pass", "comment": "人物行为是否符合设定"}},
    "setting_consistency": {{"score": 7, "status": "warning", "comment": "境界/技能/位置是否前后一致"}},
    "pacing": {{"score": 8, "status": "pass", "comment": "节奏是否合适"}},
    "hooks": {{"score": 9, "status": "excellent", "comment": "钩子和悬念是否到位"}},
    "outline_alignment": {{"score": 8, "status": "pass", "comment": "本章内容与大纲节点目标的匹配度"}}
  }},
  "issues": [{{"type": "warning", "description": "具体问题描述，如：林默在第X章记录位置为青云城，本章却出现在远水城"}}],
  "suggestions": ["具体可操作的修改建议"],
  "summary": "整体评价一句话"
}}"""

        try:
            response = await self._call_ai(
                system,
                prompt,
                max_tokens=max_tokens_chapter_quality_check(large_context),
                context={"operation": "quality_check", "chapter_title": chapter_title, "attempt": 1},
                task="quality.check",
            )
        except Exception as first_exc:
            try:
                response = await self._call_ai(
                    system,
                    prompt + "\n\n请重新质检一次：若第一次思路有偏差，以情节档案与当前章节正文为最高优先级。",
                    max_tokens=max_tokens_chapter_quality_check(large_context),
                    context={"operation": "quality_check", "chapter_title": chapter_title, "attempt": 2},
                    task="quality.check",
                )
            except Exception as second_exc:
                return {
                    "overall_score": 0,
                    "dimensions": {},
                    "issues": [],
                    "suggestions": [],
                    "summary": "质检服务暂时不可用，请稍后重试",
                    "error": f"quality_check_upstream_error: {first_exc.__class__.__name__}/{second_exc.__class__.__name__}",
                }
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
                "overall_score": 0,
                "raw_response": response,
                "error": "Failed to parse AI response"
            }

    # ── 多章节连贯性检测 ────────────────────────────────
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
}}"""

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

    async def apply_coherence_revisions(
        self,
        *,
        project_title: str,
        coherence: dict,
        chapters: List[dict],
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
    async def suggest_stream(
        self,
        chapter_content: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        system = "你是经验丰富的网络小说写作顾问，帮助作者优化章节内容。"
        prompt = f"""当前章节内容（前1500字）：
{chapter_content[:1500]}

作者问题：{user_prompt}

请给出具体的修改建议和示例。"""

        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tokens_suggest_stream(self.profile),
            context={"operation": "suggest_stream"},
            task="suggest.stream",
        ):
            yield chunk

    # ── 持久化对话 ───────────────────────────────────
    async def chat_stream(
        self,
        user_prompt: str,
        context_label: str,
        context_text: str,
        chat_history: list[dict] | None = None,
    ) -> AsyncGenerator[str, None]:
        system = (
            "你是小说创作系统里的对话助手，回答必须基于用户当前打开的作品上下文。"
            "如果上下文不足，要明确说明缺失信息，并给出下一步可检查的位置。"
        )
        history_lines = []
        for item in (chat_history or [])[-12:]:
            role = "作者" if item.get("role") == "user" else "AI助手"
            content = str(item.get("content") or "").strip()
            if content:
                history_lines.append(f"{role}：{content[:1200]}")

        context_limit = 50000 if self.profile == "gemini" else 8000
        prompt = f"""【当前对话上下文：{context_label}】
{self._clip_context(context_text, 2000, context_limit) or '（未提供）'}

【最近对话】
{chr(10).join(history_lines) or '（暂无）'}

【作者问题】
{user_prompt}

请像可以连续追问的写作搭档一样回答：
1. 先直接回答问题，不要泛泛提供写作建议。
2. 引用大纲/正文/设定中的具体依据。
3. 如果用户问“怎么突破/为何如此/前后是否矛盾”，优先从当前上下文抽取因果链。
4. 不要把左侧导航菜单、按钮名称当作小说内容。
"""

        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tokens_suggest_stream(self.profile),
            context={"operation": "chat_stream"},
            task="suggest.stream",
        ):
            yield chunk

    # ── 记忆提取 ──────────────────────────────────────
    async def extract_memory(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
    ) -> List[dict]:
        system = """你是小说记忆提取助手。从章节中提取关键记忆条目，严格返回 JSON 数组。"""
        prompt = f"""从以下章节提取关键记忆条目（最多8条），返回 JSON 数组：

章节{chapter_number}《{chapter_title}》正文：
{chapter_content[:3000]}

返回格式：
[
  {{
    "memory_type": "event",
    "title": "林默获得古传承",
    "content": "林默在鬼门关意外触发古老传承，获得...",
    "tags": ["林默", "传承", "关键事件"]
  }},
  ...
]

memory_type 只能是: event / character_state / foreshadow / setting / conflict"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_extract_memory(self.profile),
            context={"operation": "extract_memory", "chapter_title": chapter_title},
            task="debrief.extract_memory",
        )
        try:
            text = response.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception:
            return []

    # ── 大纲展开（五要素卡片）─────────────────────────
    async def expand_outline(
        self,
        node_title: str,
        node_type: str,              # volume / legacy arc
        node_summary: str,
        project_title: str,
        genre: str,
        world_summary: str,
        character_summary: str,
        theme_statement: str = "",
        existing_chapters: int = 0,  # 已有章节数，用于章节编号连续
        chapter_count: int = 10,     # 生成几章
        global_outline_context: str = "",
        previous_chapters_context: str = "",
        continuity_state: str = "",
        batch_goal: str = "",
        prior_volumes_plot_context: str = "",       # 当前卷之前各卷已落库章纲（情节链）
        prior_foreshadow_ledger: str = "",          # 前文伏笔汇总 + 伏笔表未回收项
        realm_whitelist: list[str] | None = None,   # 项目合法境界名白名单
        protagonist_state: str = "",                 # 主角当前结构化状态（境界/位置/持有物）
    ) -> dict:
        """
        为选定的大纲节点（卷或旧篇）生成详细的子章节计划。
        返回「五要素」格式：开篇钩子/核心事件/人物变化/伏笔管理/章末钩子。
        """
        def _genre_guardrail_text(raw_genre: str) -> str:
            genre_text = (raw_genre or "").strip()
            if any(tag in genre_text for tag in ["玄幻", "仙侠", "古风", "武侠"]):
                return (
                    "【类型硬约束】\n"
                    "当前题材为东方玄幻/仙侠/古风体系。禁止现代科幻词汇与设定漂移。\n"
                    "严禁出现或暗示以下表达：首席工程师、机械改造/半机械人、飞船/战舰、AI/人工智能、芯片、量子、基因实验室、星际文明、控制台、程序上传。\n"
                    "如需表达复杂遗迹或中枢，请改写为阵法中枢、古禁制、神纹、天机枢纽、血祭法坛、傀儡机关等东方玄幻语汇。"
                )
            return (
                "【类型一致性】\n"
                "保持题材语汇与世界观风格稳定，不得突然引入与当前题材冲突的现代科技设定。"
            )

        system = """你是拥有30年经验的网络小说策划，深刻理解网文追读机制。
你的大纲必须让每一章都有存在的理由，特别是「章末钩子」——
那是让读者无法放下手机的最后一句话的设计意图。
严格返回 JSON，不要任何额外文字。"""

        start_num = existing_chapters + 1
        global_context = (
            f"\n【全书卷线蓝图】\n{global_outline_context[:2000]}\n"
            if global_outline_context else ""
        )
        previous_context = (
            f"\n【已生成章节上下文（含前卷/本卷最近章节）】\n{previous_chapters_context[:2600]}\n"
            if previous_chapters_context else ""
        )
        continuity_context = (
            f"\n【滚动连续性账本】\n{continuity_state[:1800]}\n"
            if continuity_state else ""
        )
        batch_goal_context = (
            f"\n【本批任务边界】\n{batch_goal[:800]}\n"
            if batch_goal else ""
        )
        plot = (prior_volumes_plot_context or "").strip()
        prior_plot_block = (
            f"\n【前几卷已规划章纲（情节链；勿重复已发生核心事件）】\n{plot[:18000]}\n"
            if plot else ""
        )
        ledger = (prior_foreshadow_ledger or "").strip()
        prior_ledger_block = (
            f"\n【前几卷伏笔台账（未收束线索须在本卷章纲中继续埋/收）】\n{ledger[:10000]}\n"
            if ledger else ""
        )
        protagonist_state_context = (
            f"\n【主角当前状态（结构化硬约束，优先级高于任何叙事摘要）】\n{protagonist_state}\n"
            if protagonist_state else ""
        )
        # 境界白名单约束块
        _TRADITIONAL_FORBIDDEN = [
            "合体", "炼气", "筑基", "金丹", "元婴", "化神", "渡劫", "大乘",
            "练气", "开光", "融合", "心动", "紫府", "婴变", "问鼎", "登仙",
        ]
        if realm_whitelist:
            whitelist_str = "、".join(sorted(realm_whitelist))
            forbidden_hits = "、".join(_TRADITIONAL_FORBIDDEN)
            realm_constraint_block = (
                f"\n【境界体系强约束 — 必须严格遵守，违反即破坏世界观】\n"
                f"本项目专属境界白名单（character_change 中描述境界突破/状态，只能使用这些术语）：\n"
                f"{whitelist_str}\n"
                f"绝对禁止使用以下传统修真术语（来自其他IP，与本项目境界体系冲突）：\n"
                f"{forbidden_hits}\n"
                f"若需描述突破，从白名单中取词；若找不到合适词，用「主角修为提升」代替，不得自造术语。\n"
            )
        else:
            realm_constraint_block = ""
        prompt = f"""小说：《{project_title}》（{genre}）
当前节点：{node_type == 'volume' and '卷' or '旧篇'}《{node_title}》
节点概述：{node_summary or '（未填写）'}

世界观摘要：{world_summary[:400]}
主要人物（主线核心卡司，非全书全部人物——配角可按剧情需要随时引入）：{character_summary[:500]}
全书立意：{theme_statement[:300] or '（未填写；请从创意和人物中提炼一条贯穿全书的价值命题）'}
{realm_constraint_block}{protagonist_state_context}{global_context}{prior_plot_block}{prior_ledger_block}{previous_context}{continuity_context}{batch_goal_context}
请为本{node_type == 'volume' and '卷' or '旧篇'}生成 {chapter_count} 个章节计划，章节编号从第{start_num}章开始。
{_genre_guardrail_text(genre)}

每章使用「作家五要素」格式，返回 JSON：
{{
  "volume_analysis": {{
    "emotional_arc": "情绪弧线，如：压迫→绝境→逆转→升华",
    "core_question": "本卷核心悬念（读者最想知道的答案）",
    "pacing_rhythm": "节奏说明，如：前3章快节奏建立冲突，中间4章展开，末3章爆发"
  }},
  "chapters": [
    {{
      "number": {start_num},
      "title": "章节标题（有冲击力，可带悬念）",
      "opening_hook": "开篇钩子：前500字的核心手段。例：用主角被宣判死刑的场面倒叙开篇",
      "core_event": "核心事件：这章存在的理由，删掉会损失什么",
      "character_change": "人物变化：谁的认知/处境/关系发生了不可逆变化",
      "foreshadow": "伏笔管理：本章新埋的伏笔 / 回收的旧伏笔（格式：埋[xxx] 收[xxx]）",
      "end_hook": "章末钩子：读者读完最后一句停不下来的原因，要具体到手法",
      "pacing": "fast/medium/slow",
      "word_estimate": 2300
    }}
  ]
}}

重点要求：
1. 每章「章末钩子」必须具体，不能只写"留下悬念"，要说清楚「悬念的具体内容」
2. 每章字数预估控制在 2200-2400 字，默认 2300 字
3. 每章核心事件必须同时服务于情节推进、人物变化和全书立意，不要只堆事件
4. 前3章追读钩子要特别强
5. 伏笔要有连续性，本卷内至少有2条贯穿始终的伏笔线
6. 如果提供了已生成章节上下文或滚动连续性账本，必须承接上一批章末钩子、人物状态和未回收伏笔，不得重复已发生的核心事件
7. 本批第一章要自然回应上一批最后一章留下的具体悬念；如果处于新卷开头，则先承接全书卷线蓝图再开启本卷核心问题
8. 若提供了「前几卷已规划章纲」：不得复述或改头换面重复前序已写核心事件；新卷情节在其上推进
9. 若提供了「前几卷伏笔台账」：本卷各章 foreshadow 字段须点名埋/收，优先处理台账中高优先级仍未回收条目，并与章纲五要素一致"""

        max_tok = max_tokens_expand_outline(self.profile)
        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tok,
            context={"operation": "expand_outline", "node_title": node_title},
            task="outline.expand",
        )
        try:
            import re
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = min(
                (text.find("{") if text.find("{") != -1 else len(text)),
                (text.find("[") if text.find("[") != -1 else len(text)),
            )
            return json.loads(text[start:])
        except Exception as e:
            return {"error": str(e), "raw": response[:500]}

    async def outline_quality_check(
        self,
        project_title: str,
        genre: str,
        scope: str,
        node_title: str,
        chapters: list[dict],
        global_outline_context: str = "",
        previous_chapters_context: str = "",
        continuity_state: str = "",
        node_summary: str = "",
        theme_statement: str = "",
        story_bible_context: str = "",
        word_budget_context: str = "",
    ) -> dict:
        """
        大纲质检：检查卷内/全书章节计划的连续性，并返回可定位、可修复的问题列表。
        """
        chapter_lines = []
        for ch in chapters:
            chapter_lines.append(
                " | ".join([
                    f"第{ch.get('number', '?')}章：{ch.get('title', '未命名')}",
                    f"核心事件：{ch.get('core_event', '')}",
                    f"人物变化：{ch.get('character_change', '')}",
                    f"伏笔：{ch.get('foreshadow', '')}",
                    f"章末钩子：{ch.get('end_hook', '')}",
                ])
            )

        system = "你是资深长篇网文主编，专门做大纲质检和结构化修订建议。严格返回JSON，不要任何额外文字。"
        prompt = f"""小说：《{project_title}》（{genre}）
质检范围：{scope}
当前节点：{node_title}
节点概述：{node_summary or '（未填写）'}
全书立意：{theme_statement or '（未填写）'}

【故事圣经账本】
{self._clip_context(story_bible_context, 1800, None, field_name="story_bible") or '（未提供）'}

【全书卷线蓝图】
{self._clip_context(global_outline_context, 3000, None, field_name="global_outline") or '（未提供）'}

【前文/已有章节上下文】
{self._clip_context(previous_chapters_context, 3000, None, field_name="previous_chapters") or '（未提供）'}

【滚动连续性账本】
{self._clip_context(continuity_state, 2200, None, field_name="continuity_state") or '（未提供）'}

【篇幅与字数约束】
{self._clip_context(word_budget_context, 600, None, field_name="word_budget") or '（未提供）'}

【待质检章节计划】
{self._clip_context(chr(10).join(chapter_lines), 12000, None, field_name="chapter_lines_quality")}

请检查：
1. 卷内连续性：章节因果是否断裂、是否重复同类事件、人物状态是否跳变
2. 跨卷承接：是否回应前卷/前批章末钩子，是否提前透支后续卷爆点
3. 伏笔：新埋/回收是否清楚，是否出现只埋不管、无来源回收、重复伏笔
4. 人物弧：人物选择、代价、关系变化是否逐步推进
5. 节奏与追读：开篇钩子、章末钩子、高潮分布是否支撑追读
6. 全书立意：核心事件是否服务主题，而不是单纯堆事件
7. 故事圣经一致性：角色死亡/封印/失踪后再登场必须有明确机制；核心道具、力量体系、势力目标、世界规则和人物弧线不得被后续章节随意否定
8. 篇幅兑现：检查当前大纲是否支撑目标字数，重点识别中后期节奏压缩（如跨位面速刷、关键成长阶段被跳过）

返回JSON：
{{
  "scope": "{scope}",
  "overall_score": 0,
  "status": "pass/warning/fail",
  "summary": "一句话总结",
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "type": "continuity/duplicate_event/hook_continuity/foreshadow/character_arc/pacing/theme_alignment",
      "chapter_numbers": [1],
      "description": "问题说明，要具体到章节和原因",
      "suggested_patch": {{
        "chapter_number": 1,
        "field": "opening_hook/core_event/character_change/foreshadow/end_hook",
        "replacement": "建议替换文本；如不适合单字段修复，则写空字符串"
      }}
    }}
  ],
  "must_fix_chapter_numbers": [1],
  "strengths": ["做得好的地方"]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_outline_quality_check(self.profile),
            context={"operation": "outline_quality_check", "scope": scope, "node_title": node_title},
            task="quality.outline_check",
        )
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start == -1:
                raise ValueError("No JSON object found")
            return json.loads(text[start:])
        except Exception as e:
            return {"error": str(e), "raw": response[:500]}

    async def outline_repair_plan(
        self,
        project_title: str,
        genre: str,
        scope: str,
        quality_report: dict,
        chapters: list[dict],
        story_bible_context: str = "",
        global_outline_context: str = "",
        word_budget_context: str = "",
    ) -> dict:
        chapter_lines = []
        for ch in chapters:
            chapter_lines.append(
                " | ".join([
                    f"第{ch.get('number', '?')}章：{ch.get('title', '未命名')}",
                    f"开篇钩子：{ch.get('opening_hook', '')}",
                    f"核心事件：{ch.get('core_event', '')}",
                    f"人物变化：{ch.get('character_change', '')}",
                    f"伏笔：{ch.get('foreshadow', '')}",
                    f"章末钩子：{ch.get('end_hook', '')}",
                ])
            )

        system = "你是资深网文大纲修复主编。你只输出可应用的大纲字段补丁，严格返回JSON。"
        prompt = f"""小说：《{project_title}》（{genre}）
修复范围：{scope}

【故事圣经账本】
{self._clip_context(story_bible_context, 1800, None, field_name="story_bible") or '（未提供）'}

【全书卷线蓝图】
{self._clip_context(global_outline_context, 5000, None, field_name="global_outline") or '（未提供）'}

【篇幅与字数约束】
{self._clip_context(word_budget_context, 600, None, field_name="word_budget") or '（未提供）'}

【质检问题】
{self._clip_context(json.dumps(quality_report, ensure_ascii=False), 6000, None, field_name="quality_report")}

【相关章节计划】
{self._clip_context(chr(10).join(chapter_lines), 10000, None, field_name="chapter_lines_repair")}

请生成大纲修复补丁，要求：
1. 只修复质检指出的问题章节，不要整本重写，不要改无关亮点。
2. 如果问题跨多章，按章节分别给出 patch；每个 patch 必须能独立应用。
3. 修复要保持世界观、人物状态、道具象征、伏笔承接和下一卷钩子一致。
4. 每个字段必须是可直接替换的短文本，不写解释性长文。
5. 修复后要保持篇幅兑现能力：不能把中后期关键阶段压缩成速刷；必要时通过补强过渡与代价链来恢复长篇承载力。

返回JSON：
{{
  "summary": "本轮修复概述",
  "patches": [
    {{
      "chapter_number": 55,
      "fields": {{
        "opening_hook": "新的开篇钩子",
        "core_event": "新的核心事件",
        "character_change": "新的人物变化",
        "foreshadow": "新的伏笔管理",
        "end_hook": "新的章末钩子"
      }},
      "reason": "为什么这样修"
    }}
  ]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_outline_quality_check(self.profile),
            context={"operation": "outline_repair_plan", "scope": scope},
            task="outline.full_structure",
        )
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start == -1:
                raise ValueError("No JSON object found")
            data = json.loads(text[start:])
            if not isinstance(data.get("patches"), list):
                data["patches"] = []
            return data
        except Exception as e:
            return {"error": str(e), "raw": response[:500], "patches": []}

    # ── 全量大纲：第一步生成卷级结构 ──────────────────
    async def plan_full_structure(
        self,
        project_title: str,
        genre: str,
        logline: str,
        world_summary: str,
        character_summary: str,
        theme_statement: str = "",
        scale_hint: str = "auto",   # 保留兼容，不再驱动计算
        target_words: int = 1_200_000,  # 单一数据源
    ) -> dict:
        """
        全量大纲规划：AI 规划卷结构，后端按 target_words 校准章节数。
        返回: { "volumes": [{ title, summary, hook, conflict, planned_chapters: int }] }
        """
        from app.services.outline_planning import words_to_plan
        tw_plan = words_to_plan(target_words)
        total_chapters_hint = tw_plan["total_chapters"]
        n_volumes = tw_plan["total_volumes"]

        system = "你是资深网络小说策划，擅长根据故事特质规划最合适的卷章结构。严格返回JSON，不要任何额外文字。"
        prompt = f"""小说：《{project_title}》（{genre}）
一句话创意：{logline or '（未填写）'}
全书立意：{theme_statement[:500] or '（未填写；请从创意和人物中提炼一条贯穿全书的价值命题）'}
世界观：{world_summary[:300] or '（未填写）'}
主要人物：{character_summary[:200] or '（未填写）'}

【字数目标】全书目标：{target_words:,}字，折合约{total_chapters_hint}章；**必须恰好规划 {n_volumes} 卷**（由目标字数推算，不得增减卷数；卷较少时合并 phase，禁止为凑阶段而加卷）。

请根据这个故事的特质规划卷级结构。
章节数必须服务于「每卷约 60 章、每章 2200-2400 字」的长篇目录结构：planned_chapters 优先使用 60，必要时允许 30，不要使用篇/arc结构。
所有卷的 planned_chapters 之和须尽量接近{total_chapters_hint}章。
每卷必须围绕全书立意形成一个阶段性证明：人物选择如何变化，价值冲突如何升级，不能只做事件堆叠。

返回JSON：
{{
  "volumes": [
    {{
      "title": "卷标题（简洁有力，带悬念感，不要用"第X卷"）",
      "summary": "本卷核心情节摘要，60字内",
      "theme_stage": "本卷如何推进/反证/深化全书立意",
      "character_arc": "本卷关键人物的欲望、选择和代价",
      "hook": "本卷核心悬念：读者最想知道答案的问题",
      "conflict": "本卷主要矛盾冲突",
      "planned_chapters": 60
    }}
  ]
}}

规划原则：
1. 不再使用“篇”的概念；直接规划“卷 → 章”
2. 每卷优先 60 章，少数过渡卷可以 30 章；不要随意给 10、15、20、40 这类杂乱数量
3. 每章按 2200-2400 字设计，优先按 2300 字估算
4. 整体弧线完整，起承转合清晰，收尾不要仓促
5. 人物弧线、剧情主线、世界观秘密都要受全书立意统领
6. 悬念递进，每卷末尾都要有足够的钩子让读者追下一卷
7. 标题要有画面感，能让读者一眼感受到本卷的核心氛围"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_plan_full_structure(self.profile),
            context={"operation": "plan_full_structure"},
            task="outline.full_structure",
        )
        import re
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start == -1:
                raise ValueError("No JSON object found")
            return json.loads(text[start:])
        except Exception as e:
            return {"error": str(e), "raw": response[:500]}

    # ── AI 辅助写作（流式）────────────────────────────
    async def draft_assist_stream(
        self,
        chapter_title: str,
        outline_hook: str,
        outline_summary: str,
        outline_conflict: str,
        outline_highlight: str,
        outline_foreshadow: str,
        prev_chapter_tail: str,
        world_summary: str,
        character_summary: str,
        memory_summary: str,
        existing_content: str,
        premise: str = "",
        user_prompt: str = "",
        replace_existing: bool = False,
        # 故事线、实力里程碑、情感基调
        storyline_summary: str = "",
        outline_power_milestone: str = "",
        outline_emotional_tone: str = "",
        # 第二道锁：本章故事日 + 人物清单约束
        story_day: str = "",
        chapter_manifest: list = None,
        # 生成前从数据库整理出的事实账本，约束跨章连续性
        continuity_context: str = "",
        chapter_index_context: str = "",
        quality_debt_context: str = "",
        writing_brief_context: str = "",
        # 线索页「伏笔管理」+ 章节索引情节档案（与质检同源），独立预算避免被连续性账本截断
        plot_dossier_context: str = "",
        # 本章字数目标（来自 OutlineNode.expected_words）
        word_target: int = 2300,
        # 卷阶段（OutlineNode.phase / volume.extra.phase），用于切 prompt 模板与采样档位
        phase: Optional[str] = None,
        # 立项定位（Project.extra.positioning），用于把读者画像 / 爽点节奏注入 prompt
        positioning: Optional[dict] = None,
        # 写入 llm_call_logs.context，便于对账（含模型完整原文 output_payload.text）
        stream_log_context: dict | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        根据大纲计划 + 完整故事上下文，流式生成本章起笔或续写建议。
        像一位有30年经验的作家，把世界观、人物弧、伏笔、故事线进展自然织入文字。

        Args:
            phase: 卷阶段，决定模板分支与采样档位。
                可选：``opening`` / ``rising`` / ``turning`` / ``dark_hour`` / ``climax`` / ``ending``。
                未提供时按"中段章节"模板写。
            positioning: ``Project.extra.positioning`` JSON——读者画像 / 爽点类型 / 打脸频率 / 情感线占比 /
                节奏类型。用于把作品基本面注入正文 prompt，避免每章独立漂移。
        """
        from app.services.llm_task_profiles import phase_to_draft_task

        has_content = bool(
            not replace_existing and existing_content and len(existing_content.strip()) > 50
        )
        large_context = self._large_context_enabled()

        # ── 阶段化 system prompt：开篇/起飞/转折/至暗/高潮/收束 各有侧重 ────────────
        phase_norm = (phase or "").strip().lower()
        phase_brief_map = {
            "opening": (
                "【当前卷阶段：开局期 / 新手村】\n"
                "- 钩子密度高：每 800-1000 字至少一个张力点（疑问、压迫、伏笔、冲突）\n"
                "- 信息密度高：开篇 200 字内必须落地世界、主角状态、核心痛点\n"
                "- 爽点节奏：3 章一小爽，禁止纯铺垫章；当章必须有可被读者复述的「高光瞬间」\n"
                "- 字数偏短（建议 ±200 字内贴近 2200 字），节奏要紧；忌用大段心理流水账"
            ),
            "rising": (
                "【当前卷阶段：起飞期 / 扩张期】\n"
                "- 势力面扩展、感情线接入；每章保留至少一条 hook\n"
                "- 允许中等节奏的铺垫，但必须有「小爽收束」或反转预告\n"
                "- 控制信息量，避免一章塞太多新设定"
            ),
            "turning": (
                "【当前卷阶段：转折期】\n"
                "- 推进核心矛盾升级；老角色态度转变；至少一处反转或代价兑现\n"
                "- 节奏中速，对话比心理多；不要回避负面情绪"
            ),
            "dark_hour": (
                "【当前卷阶段：至暗期】\n"
                "- 允许「虐」，节奏放缓，让代价具象、让选择艰难\n"
                "- 主角处境恶化，不要急于反弹；情绪基调克制不浮夸\n"
                "- 字数可适度拉长（接近 2800 字），多用具体场景渲染压力"
            ),
            "climax": (
                "【当前卷阶段：高潮期】\n"
                "- 所有伏笔在本卷内必须给读者明确反馈（回收 / 提级 / 公开）\n"
                "- 爆点拉满：动作 / 情绪 / 信息揭示三选二；字数允许 3000-3300 字\n"
                "- 章末必须留下卷尾级钩子（更大反派 / 新地图 / 关键人物动向）"
            ),
            "ending": (
                "【当前卷阶段：收束期】\n"
                "- 给读者交代感，但保留下一卷悬念种子\n"
                "- 不要总结性独白；用一个画面或对话句结束本章"
            ),
        }
        phase_brief = phase_brief_map.get(phase_norm, "")

        # ── 立项定位：读者画像 / 爽点类型 / 节奏（每章都要看见，不再让 AI 临场猜）────────
        positioning_brief = ""
        if positioning and isinstance(positioning, dict):
            parts = []
            if positioning.get("target_audience"):
                parts.append(f"目标读者：{positioning['target_audience']}")
            if positioning.get("tropes"):
                tropes = positioning["tropes"]
                if isinstance(tropes, list):
                    tropes = "、".join(str(t) for t in tropes if t)
                parts.append(f"核心爽点类型：{tropes}")
            if positioning.get("face_slap_pattern"):
                parts.append(f"打脸频率：{positioning['face_slap_pattern']}")
            if positioning.get("emotional_arc"):
                parts.append(f"情感线占比：{positioning['emotional_arc']}")
            if positioning.get("pace_type"):
                parts.append(f"节奏类型：{positioning['pace_type']}")
            if positioning.get("selling_point"):
                parts.append(f"卖点钩子：{positioning['selling_point']}")
            if parts:
                positioning_brief = "【作品基本面（必须每章贯彻）】\n" + "\n".join(parts)

        system = """你是拥有30年经验的网络小说作家，文笔老练，深谙追读节奏。
你的任务是根据章节计划和故事背景，为作者提供一段高质量的正文文字。

写作原则：
1. 严格遵循「开篇钩子」意图，第一句话就要抓人
2. 世界观、人物当前境界和状态要自然融入，不要与已知人物设定矛盾
3. 人物的行动和心理要符合其弧线和动机
4. 注意上一章结尾的衔接，保持情感和节奏的连续性
5. 如果本章有实力里程碑（如突破境界），要让这一刻有分量
6. 故事线进展要顺势推进，切勿无视当前活跃的冲突线
7. 每一场戏都必须服务作品基本面：读者定位、核心命题、爽点承诺、禁忌边界
8. 写完正文后，必须追加「章节速查索引」区块，使用固定模板，便于后续复盘与连续性追踪
9. 直接给出正文，不要解释、不要旁白、不要说"好的"之类的废话

【章末钩子硬约束（必须遵守）】
- 章节最后一段（不超过 80 字）必须满足以下之一：
  A) 出现新的未解之谜或揭示
  B) 强敌 / 关键 NPC 登场但未交手
  C) 关键人物开口未说完，话被掐断
  D) 主角被推到决策悬崖（必须立刻选）
- 严禁章末用总结句、抒情句、陈述性收束（如"夜更深了""一切归于平静"）
- 钩子必须紧贴正文事件，不允许另起一段意义不明的"画外音"

【反面例子 / 严禁清单】
- 严禁流水账连接词："然后……接着……于是……此时……"
- 严禁排比式抒情开篇："少年抬头望向天空""天地间一片寂静""时间仿佛静止"
- 严禁单段心理独白超过 200 字
- 严禁解释性旁白连续 3 句以上（让事件本身说话）
- 严禁滥用"突然"作为段落起点
- 严禁出现 AI 自指词（"作为一个 AI""根据您的要求""我来为您"）"""

        if positioning_brief:
            system = system + "\n\n" + positioning_brief
        if phase_brief:
            system = system + "\n\n" + phase_brief

        # 根据大纲 word_target 动态计算续写字数
        full_target = max(1500, int(word_target or 2300))
        cont_target_lo = max(800, round(full_target * 0.5))
        cont_target_hi = max(1200, round(full_target * 0.7))

        if replace_existing:
            task_line = (
                f"【整章重写】请根据本章大纲与故事背景，写出全新正文约{full_target}字（±200字），"
                "不要复述或抄袭旧稿套话；若旧稿与大纲冲突，以大纲为准。"
            )
        elif has_content:
            existing_tail_limit = 4000 if large_context else 500
            task_line = (
                f"当前已写内容（最后{existing_tail_limit}字供衔接参考）：\n"
                f"{self._clip_context(existing_content, 500, 4000, from_end=True)}\n\n"
                f"请根据章节计划，续写接下来约{cont_target_lo}-{cont_target_hi}字的正文，保持章节爽点与情绪推进："
            )
        else:
            task_line = f"请根据章节计划，写出本章完整初稿约{full_target}字（±200字），第一句话必须立刻抓住读者，并在章末留下追读钩子："

        # 本地小模型仍保持短上下文；Gemini 使用长上下文，优先保证故事连续性。
        premise_part = (
            self._clip_context(premise, 1200, 12000)
            if premise
            else "（未填写；请从创意、人物和大纲中提炼作品基本面，但不得违背既有设定）"
        )
        world_part = self._clip_context(world_summary, 200, 12000) if world_summary else "（未设定）"
        char_part = self._clip_context(character_summary, 300, 12000) if character_summary else "（未设定）"
        mem_part = (
            f"\n近期关键事件：{self._clip_context(memory_summary, 150, 12000)}"
            if memory_summary else ""
        )
        prev_part = (
            self._clip_context(prev_chapter_tail, 300, 4000, from_end=True)
            if prev_chapter_tail else "（这是第一章，无前情）"
        )
        continuity_part = (
            f"\n【连续性账本 / 不得违背】\n{self._clip_context(continuity_context, 2000, 24000)}\n"
            if continuity_context
            else ""
        )
        chapter_index_part = (
            f"\n【章节速查索引】\n{self._clip_context(chapter_index_context, 1600, 20000)}\n"
            if chapter_index_context
            else ""
        )
        plot_dossier_part = (
            f"\n【情节档案 / 伏笔管理表与故事线】\n"
            f"{self._clip_context(plot_dossier_context, 2200, 30000)}\n"
            if plot_dossier_context
            else ""
        )
        quality_debt_part = (
            f"\n{self._clip_context(quality_debt_context, 1200, 12000)}\n"
            if quality_debt_context
            else ""
        )
        writing_brief_part = (
            f"\n{self._clip_context(writing_brief_context, 1200, 20000)}\n"
            if writing_brief_context
            else ""
        )

        # 故事线与本章特殊目标
        storyline_part = (
            f"\n当前活跃故事线：{self._clip_context(storyline_summary, 200, 8000)}"
            if storyline_summary else ""
        )
        milestone_part = f"\n本章实力里程碑：{outline_power_milestone}" if outline_power_milestone else ""
        tone_part = f"\n情感基调：{outline_emotional_tone}" if outline_emotional_tone else ""
        day_part = f"\n故事日：{story_day}" if story_day else ""

        # 第二道锁：人物清单硬约束
        # chapter_manifest 有值 = 新大纲数据，启用严格模式
        # 为空 = 旧大纲/无清单，退回兼容模式（不加约束）
        manifest_constraint = ""
        if chapter_manifest:
            manifest_str = "、".join(chapter_manifest)
            manifest_constraint = (
                f"\n\n⚠️【本章人物清单（严格限定）】\n"
                f"本章允许出场的命名角色：{manifest_str}\n"
                f"不得引入清单之外的任何命名角色。"
                f"若剧情需要路人/次要角色，用「一名弟子」「路人」等无名方式处理。"
            )

        extra = ""
        if user_prompt and user_prompt.strip():
            extra = f"\n\n【作者补充要求】\n{self._clip_context(user_prompt, 800, 4000)}"

        index_template = """
【章节速查索引输出模板（必须追加在正文结尾）】
### ch_章节号（3位补零）　章节标题
**核心事件**：
1. 事件1
2. 事件2
3. 事件3
**首次出场**：角色A（身份）
**章末钩子强度**：⭐到⭐⭐⭐⭐⭐（并在括号内写一句钩子描述）
**伏笔埋设**：F-编号（伏笔描述，ch_回收章号回收）
"""

        prompt = f"""【立意与类型 / PREMISE】
{premise_part}

【故事背景】
世界观：{world_part}
本章出场人物（含境界/位置/技能）：{char_part}{mem_part}{storyline_part}
{writing_brief_part}

【上章结尾】
{prev_part}
{continuity_part}
{chapter_index_part}
{plot_dossier_part}
{quality_debt_part}

【本章大纲计划】
标题：{chapter_title}{day_part}
开篇钩子：{outline_hook or "（未填写）"}
核心事件：{outline_summary or "（未填写）"}
人物变化：{outline_conflict or "（未填写）"}
章末方向：{outline_highlight or "（未填写）"}{milestone_part}{tone_part}
{f"伏笔管理：{outline_foreshadow}" if outline_foreshadow else ""}{manifest_constraint}

{task_line}
{index_template}{extra}"""

        max_tok = max_tokens_draft_stream(large_context)
        stream_ctx: dict = {
            "operation": "draft_assist_stream",
            "chapter_title": chapter_title,
            "phase": phase_norm or None,
        }
        if stream_log_context:
            stream_ctx.update(stream_log_context)
        # 阶段→任务名映射：开局期/高潮期/至暗期分别走更激进或更克制的采样档位
        draft_task = phase_to_draft_task(phase_norm)
        async for chunk in self._stream_ai(
            system,
            prompt,
            max_tokens=max_tok,
            context=stream_ctx,
            task=draft_task,
        ):
            yield chunk

    # ── 自动复盘提取 ──────────────────────────────────
    async def auto_extract_debrief(
        self,
        chapter_content: str,
        chapter_title: str,
        chapter_number: int,
        character_states: List[dict],    # [{"id":…,"name":…,"current_realm":…,"current_location":…,"current_status":…}]
        storylines: List[dict],          # [{"id":…,"name":…,"line_type":…,"status":…,"core_conflict":…}]
    ) -> dict:
        """
        AI 读取章节正文，对照人物当前状态和故事线，
        自动提取本章发生的状态变化和故事节拍。
        返回结构化建议供前端预填复盘表单。
        """
        # 精简人物列表（token 控制）
        char_lines = []
        for c in character_states[:10]:
            parts = [f"- {c['name']}（id:{c['id']}）"]
            if c.get("current_realm"):
                parts.append(f"境界:{c['current_realm']}")
            if c.get("current_location"):
                parts.append(f"位置:{c['current_location']}")
            if c.get("current_status"):
                parts.append(f"状态:{c['current_status']}")
            char_lines.append("".join(parts))
        chars_text = "\n".join(char_lines) or "（无人物数据）"

        sl_lines = [
            f"- {s['name']}（id:{s['id']}，{s['line_type']}，当前:{s['status']}）：{(s.get('core_conflict') or '')[:60]}"
            for s in storylines[:8]
        ]
        sl_text = "\n".join(sl_lines) or "（无故事线数据）"

        system = (
            "你是网络小说助手，从章节内容中提取人物状态、故事线、伏笔、信息来源和结构化资产变化，只返回JSON，不要任何解释。"
            "语言：除 JSON 键名、以及各字段说明中要求使用的英文枚举值（如 alive/dead、open、planned/active/climax/resolved/dropped、"
            "low/medium/high、item_type/rarity 等）外，所有人类可读的自然语言字符串必须使用简体中文——含 memory_updates 的 title/content/tags、"
            "storyline_updates.beat、chapter_index 全部文案（含 story_day）、asset_updates 与 new_characters 中的描述字段、summary 等。"
            "不得用英文撰写剧情摘要、伏笔说明或章末钩子；专有名词（人名、功法、法宝、地名）与正文用字保持一致。"
        )

        narrative_body = self._clip_context(
            (chapter_content or "").strip(),
            12000,
            120000,
        )

        prompt = f"""章节{chapter_number}《{chapter_title}》

【叙事正文】（业务库仅存叙事；须通读下列全文以提取人物、故事线、资产与记忆；稿末模板仅保留在模型调用记录中供对账）
{narrative_body}

当前人物状态（对照基准）：
{chars_text}

当前故事线（对照基准）：
{sl_text}

请分析本章内容，提取：
1. 哪些人物的境界/位置/状态发生了变化
2. 哪些人物习得了新技能
3. 哪些故事线有了推进（节拍）
4. 哪些信息来源需要记录，避免后文凭空知道信息
5. 哪些伏笔被埋下或回收，避免后文突然出现无前因的设定（chapter_index 中回收条目须在 description 内写明全局伏笔编号 **F-xxx**，以便更新伏笔管理表；新埋伏笔建议同样带 **F-编号：** 前缀以便对齐）
6. 哪些新道具/法宝、功法/技能、势力需要收入系统，或已有资产状态发生变化
7. 生成章节索引（chapter_index）：完全依据上方叙事正文归纳；须与正文事实一致
8. 本章是否出现了不在现有角色库中、且值得长期追踪的新角色（new_characters）
   判断标准：正文中有名有姓、有台词或行动、且 arc_scope 为 mini_arc 或以上；纯工具性一次性路人不需要入库

只提取文中明确发生的变化，不要推断或猜测。
如果某字段没有变化，不要包含它。
资产表只记录 A/B 级耐久实体：会再次出现、影响人物能力/势力关系/主线伏笔/后续冲突的道具、技能、势力。
C级临时资产（一次性丹药、普通符箓、无名小队、普通招式）不要放进 asset_updates，只可在正文或 memory_updates 中作为事件细节出现。
记忆库记录“第几章发生了什么、信息来源是什么、为何获得/使用/暴露该资产”；资产表记录“这个实体现在是什么、谁持有/掌握、能力/限制/状态是什么”。两者不要互相替代。
`character_updates.current_status` 只能填写以下枚举之一：
- alive
- dead
- missing
- sealed
- transformed
禁止输出任何附加说明，例如 "alive（受伤）"、"dead-被刺杀"、"active"。
再次强调：除上述英文枚举与 JSON 键名外，一律简体中文；story_day 用中文表述故事内时间（如「第8日」「首日·夜至晨」），勿用 Day 1 式英文。

返回JSON（严格遵守字段名）：
{{
  "character_updates": [
    {{
      "character_id": "人物id",
      "character_name": "人物名称（供显示）",
      "current_realm": "新境界（如有变化）",
      "current_location": "新位置（如有变化）",
      "current_status": "新状态（仅允许 alive/dead/missing/sealed/transformed 之一）",
      "add_skill_name": "习得的技能名（如有）",
      "add_skill_mastery": "掌握程度，如：初学/熟练/精通"
    }}
  ],
  "storyline_updates": [
    {{
      "storyline_id": "故事线id",
      "storyline_name": "故事线名称（供显示）",
      "status": "新状态 planned/active/climax/resolved/dropped（如有变化）",
      "beat": "本章该故事线发生了什么（一句话）"
    }}
  ],
  "memory_updates": [
    {{
      "memory_type": "event / character_state / foreshadow / setting / conflict 之一",
      "title": "短标题",
      "content": "可供后续生成使用的事实，必须写清信息来源、伏笔前因或状态变化",
      "tags": ["人物名", "关键词"]
    }}
  ],
  "asset_updates": {{
    "new_items": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新道具/法宝/材料名",
        "item_type": "weapon/armor/pill/artifact/material/scroll/beast/other",
        "rarity": "common/uncommon/rare/epic/legendary/mythic/unique",
        "description": "外观与性质",
        "origin": "来历（如正文明确）",
        "effects": "能力效果",
        "limitations": "限制/代价",
        "current_owner_id": "持有人物id（如能对应）",
        "current_owner_name": "持有人名（如正文明确）",
        "story_significance": "为什么值得入库",
        "status": "intact/damaged/destroyed/lost/unknown",
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "item_updates": [
      {{
        "item_id": "已有道具id（如知道）",
        "item_name": "已有道具名",
        "status": "新状态（如有）",
        "current_owner_id": "新持有人id（如有）",
        "current_owner_name": "新持有人名（如有）",
        "effects": "新增/暴露的效果（如正文明确）",
        "limitations": "新增/暴露的限制（如正文明确）",
        "story_significance": "意义变化（如有）",
        "event_note": "本章发生的资产事件"
      }}
    ],
    "new_skills": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新功法/技能名",
        "skill_type": "combat/defense/movement/support/bloodline/special",
        "grade": "mortal/earth/sky/profound/saint/divine/supreme",
        "source": "来源",
        "level_required": "境界要求",
        "prerequisites": "前置条件",
        "description": "技能描述",
        "effects": "效果",
        "limitations": "限制/代价",
        "mastered_by_character_ids": ["掌握者id"],
        "mastered_by_character_names": ["掌握者姓名"],
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "skill_updates": [
      {{
        "skill_id": "已有技能id（如知道）",
        "skill_name": "已有技能名",
        "effects": "新增/暴露的效果（如正文明确）",
        "limitations": "新增/暴露的限制（如正文明确）",
        "add_mastered_by_character_id": "新掌握者id（如有）",
        "add_mastered_by_character_name": "新掌握者姓名（如有）",
        "mastery": "掌握程度",
        "event_note": "本章发生的技能事件"
      }}
    ],
    "new_factions": [
      {{
        "tier": "A/B，C级不要输出",
        "name": "新势力名",
        "faction_type": "sect/kingdom/family/guild/evil/race/other",
        "alignment": "protagonist/neutral/antagonist/unknown",
        "description": "势力描述",
        "territory": "活动范围",
        "strength_level": "实力层级",
        "goals": "目标",
        "resources": "资源",
        "attitude_to_protagonist": "friendly/hostile/neutral/subordinate/superior",
        "reason_to_store": "入库原因，必须说明它会如何影响后文"
      }}
    ],
    "faction_updates": [
      {{
        "faction_id": "已有势力id（如知道）",
        "faction_name": "已有势力名",
        "alignment": "新阵营（如有）",
        "goals": "目标变化（如有）",
        "resources": "资源变化（如有）",
        "attitude_to_protagonist": "对主角态度变化（如有）",
        "event_note": "本章发生的势力事件"
      }}
    ]
  }},
  "new_characters": [
    {{
      "name": "姓名",
      "role": "supporting",
      "character_tier": "arc",
      "gender": "男/女",
      "age": "年龄或模糊描述",
      "faction": "所属势力或机构",
      "personality": "性格（1句话）",
      "motivation": "本章/本卷的行为动机",
      "background": "背景（1句话）",
      "current_realm": "境界或能力层级",
      "current_status": "alive",
      "current_location": "本章末位置",
      "arc_scope": "single_chapter / mini_arc / long_arc",
      "author_notes": "给作者的提醒：此角色应如何使用、何时退出、是否有伏笔价值"
    }}
  ],
  （character_tier 判断规则：
    core=核心长线，贯穿全书、长期影响主线——通常来自 Bootstrap 卡司，正文中若再度出场且展现出长期价值可升级；
    arc=弧线支柱，在某卷或某段剧情主导走向，弧线结束后淡出/离场——对应 arc_scope=mini_arc 或 long_arc；
    plot=剧情推手，短期出现推进特定节点后退场——对应 arc_scope=single_chapter 或 mini_arc 中的工具性角色；
    background=背景填充，丰富氛围无强情节绑定，极少台词/行动。
    不要全部填 arc，请按正文实际分量严格判断。）
  "chapter_index": {{
    "story_day": "故事内时间（简体中文），如「第8日」「首日（夜→晨）」；未知则为空字符串",
    "core_events": ["本章实际发生的核心事件1", "核心事件2"],
    "first_appearances": [{{"character_id": "可为空", "name": "首次出场人物名"}}],
    "actual_foreshadows_laid": [{{"description": "实际写进正文的新伏笔；建议「F-编号：悬念描述」，全新伏笔也可仅写描述由系统分配编号", "status": "open"}}],
    "actual_foreshadows_resolved": [{{"description": "本章回收的伏笔；每条必须以「F-编号：」开头（引用伏笔表中待回收条目），勿省略编号"}}],
    "ending_hook": "章末钩子描述",
    "hook_strength": 1,
    "continuity_notes": [{{"severity": "low/medium/high", "note": "生成或正文中发现的连续性风险"}}]
  }},
  "summary": "本章整体复盘总结（一句话）"
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=max_tokens_auto_debrief(self.profile),
            context={"operation": "auto_extract_debrief", "chapter_title": chapter_title},
            task="debrief.auto",
        )
        try:
            import re as _re
            text = response.strip()
            text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
            if "```" in text:
                fence = _re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            data = json.loads(text)
            # 清理空字段
            char_updates = []
            for cu in data.get("character_updates", []):
                cleaned = {k: v for k, v in cu.items() if v and k not in ("character_name",)}
                if len(cleaned) > 1:  # 除 character_id 外还有其他字段
                    cleaned["character_name"] = cu.get("character_name", "")
                    char_updates.append(cleaned)
            sl_updates = []
            for su in data.get("storyline_updates", []):
                cleaned = {k: v for k, v in su.items() if v and k not in ("storyline_name",)}
                if len(cleaned) > 1:
                    cleaned["storyline_name"] = su.get("storyline_name", "")
                    sl_updates.append(cleaned)
            memory_updates = []
            valid_memory_types = {"event", "character_state", "foreshadow", "setting", "conflict"}
            for mu in data.get("memory_updates", []):
                if not isinstance(mu, dict):
                    continue
                memory_type = mu.get("memory_type") or "event"
                if memory_type not in valid_memory_types:
                    memory_type = "event"
                content = (mu.get("content") or "").strip()
                if not content:
                    continue
                tags = mu.get("tags") if isinstance(mu.get("tags"), list) else []
                memory_updates.append({
                    "memory_type": memory_type,
                    "title": (mu.get("title") or memory_type).strip()[:120],
                    "content": content,
                    "tags": [str(t) for t in tags[:8] if str(t).strip()],
                })
            raw_assets = data.get("asset_updates") if isinstance(data.get("asset_updates"), dict) else {}

            def _clean_asset_items(key: str, limit: int = 8) -> list:
                return [
                    item for item in (raw_assets.get(key) or [])[:limit]
                    if isinstance(item, dict) and (item.get("name") or item.get("item_name") or item.get("skill_name") or item.get("faction_name"))
                ]

            asset_updates = {
                "new_items": [
                    item for item in _clean_asset_items("new_items")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "item_updates": _clean_asset_items("item_updates"),
                "new_skills": [
                    item for item in _clean_asset_items("new_skills")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "skill_updates": _clean_asset_items("skill_updates"),
                "new_factions": [
                    item for item in _clean_asset_items("new_factions")
                    if item.get("tier", "B") in ("A", "B") and item.get("name")
                ],
                "faction_updates": _clean_asset_items("faction_updates"),
            }
            chapter_index = data.get("chapter_index") if isinstance(data.get("chapter_index"), dict) else {}
            hook_strength = chapter_index.get("hook_strength", 1)
            try:
                hook_strength = max(1, min(5, int(hook_strength)))
            except Exception:
                hook_strength = 1
            cleaned_index = {
                "story_day": (chapter_index.get("story_day") or "").strip(),
                "core_events": [
                    item for item in (chapter_index.get("core_events") or [])[:5]
                    if isinstance(item, (str, dict)) and item
                ],
                "first_appearances": [
                    item for item in (chapter_index.get("first_appearances") or [])[:8]
                    if isinstance(item, dict) and (item.get("name") or item.get("character_id"))
                ],
                "actual_foreshadows_laid": [
                    item for item in (chapter_index.get("actual_foreshadows_laid") or [])[:10]
                    if isinstance(item, dict) and item.get("description")
                ],
                "actual_foreshadows_resolved": [
                    item for item in (chapter_index.get("actual_foreshadows_resolved") or [])[:10]
                    if isinstance(item, dict) and item.get("description")
                ],
                "ending_hook": (chapter_index.get("ending_hook") or "").strip(),
                "hook_strength": hook_strength,
                "continuity_notes": [
                    item for item in (chapter_index.get("continuity_notes") or [])[:10]
                    if isinstance(item, (str, dict)) and item
                ],
            }
            # 提取 new_characters，过滤掉无效项；兼容 AI 把多人写进单个 description 字段的错误格式
            raw_new_chars = data.get("new_characters") or []
            new_characters = []
            for item in raw_new_chars:
                if not isinstance(item, dict):
                    continue
                if item.get("name"):
                    new_characters.append(item)
                elif item.get("description") and not item.get("name"):
                    # AI 错误地把多人名写进了 description，尝试拆分恢复
                    desc = str(item["description"])
                    # 按中文顿号、逗号、换行、分号分割
                    import re as _re2
                    parts = _re2.split(r"[、，,；;\n]+", desc)
                    for part in parts:
                        # 取括号前的名字，如 "王虎（黑煞宗监工）" → "王虎"
                        name = _re2.split(r"[（(【]", part.strip())[0].strip()
                        if name and 1 <= len(name) <= 10:
                            new_characters.append({"name": name, "role": "supporting", "current_status": "alive"})
            new_characters = new_characters[:6]  # 单章最多6个新配角，防止失控

            return {
                "character_updates": char_updates,
                "storyline_updates": sl_updates,
                "memory_updates": memory_updates,
                "asset_updates": asset_updates,
                "new_characters": new_characters,
                "chapter_index": cleaned_index,
                "summary": data.get("summary", ""),
            }
        except Exception as e:
            return {
                "character_updates": [],
                "storyline_updates": [],
                "memory_updates": [],
                "asset_updates": {
                    "new_items": [],
                    "item_updates": [],
                    "new_skills": [],
                    "skill_updates": [],
                    "new_factions": [],
                    "faction_updates": [],
                },
                "new_characters": [],
                "chapter_index": {},
                "summary": "",
                "error": f"解析失败: {e}",
                "raw": response[:300],
            }

    # ── 底层调用 ──────────────────────────────────────
    @staticmethod
    def _is_retryable_llm_error(err: Exception) -> bool:
        status_code = getattr(err, "status_code", None)
        if isinstance(status_code, int) and status_code in (408, 429, 500, 502, 503, 504):
            return True
        msg = str(err).lower()
        return any(key in msg for key in ("error code: 502", "bad gateway", "timeout", "temporarily unavailable"))

    def _build_sampling_kwargs(
        self,
        task: Optional[str],
        sampling_overrides: Optional[dict],
    ) -> dict:
        """合并「任务级默认采样」与「调用方覆写」并剔除空值。

        - `task`：在 ``llm_task_profiles.TASK_PROFILES`` 中查表，未命中返回空 dict；
        - `sampling_overrides`：调用方临时覆写（例如某次 A/B 测试），优先级最高；
        - 空 dict / None 字段会被剔除，避免网关因不识别的空字段报错。

        返回的 dict 直接展开进 ``client.chat.completions.create(**kwargs)``。
        """
        merged = dict(resolve_task_profile(task))
        if sampling_overrides:
            for k, v in sampling_overrides.items():
                if v is not None:
                    merged[k] = v
        return {k: v for k, v in merged.items() if v is not None}

    async def _call_ai(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        context: Optional[dict] = None,
        *,
        task: Optional[str] = None,
        sampling: Optional[dict] = None,
    ) -> str:
        """非流式 LLM 调用。

        Args:
            system: 系统提示。
            prompt: 用户提示。
            max_tokens: 单次输出上限。
            context: 写入 ``llm_call_logs.context`` 的对账元数据。
            task: 任务名，用于查 ``llm_task_profiles`` 选取采样参数；缺省走网关默认。
            sampling: 调用方临时覆写采样字段（temperature/top_p/...）。

        Returns:
            模型返回的纯文本内容（不含 ``<think>``）。
        """
        client = self._get_client()
        start = time.perf_counter()
        sampling_kwargs = self._build_sampling_kwargs(task, sampling)
        try:
            # SDK 本身会重试；这里再补一层短退避，兜住网关偶发 5xx，减少工作流整体失败。
            resp = None
            last_error: Exception | None = None
            retry_delays = (0.8, 1.6)
            for attempt in range(len(retry_delays) + 1):
                try:
                    resp = await client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=max_tokens,
                        **sampling_kwargs,
                    )
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    if attempt >= len(retry_delays) or not self._is_retryable_llm_error(e):
                        raise
                    await asyncio.sleep(retry_delays[attempt])

            if resp is None:
                if last_error is not None:
                    raise last_error
                raise RuntimeError("LLM 调用失败：未获得响应")

            choices = getattr(resp, "choices", None) or []
            if not choices:
                raise RuntimeError("LLM 返回空 choices，无法读取正文")
            msg = getattr(choices[0], "message", None)
            content = (getattr(msg, "content", None) or "") if msg is not None else ""
            usage_obj = getattr(resp, "usage", None)
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
                "completion_tokens": getattr(usage_obj, "completion_tokens", None),
                "total_tokens": getattr(usage_obj, "total_tokens", None),
            } if usage_obj is not None else {}
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context={**(context or {}), "task": task, "sampling": sampling_kwargs},
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="ok",
                prompt_text=f"{system}\n{prompt}",
                completion_text=content,
                usage=usage,
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    **sampling_kwargs,
                },
                output_payload={"text": content},
                db=self._db,
            )
            return content
        except Exception as e:
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context={**(context or {}), "task": task, "sampling": sampling_kwargs},
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="error",
                prompt_text=f"{system}\n{prompt}",
                error=str(e),
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    **sampling_kwargs,
                },
                db=self._db,
            )
            raise

    async def _stream_ai(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 2048,
        context: Optional[dict] = None,
        *,
        task: Optional[str] = None,
        sampling: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """流式 LLM 调用。参数语义与 :meth:`_call_ai` 一致。"""
        client = self._get_client()
        start = time.perf_counter()
        output_chunks: List[str] = []
        sampling_kwargs = self._build_sampling_kwargs(task, sampling)
        try:
            stream = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                stream=True,
                **sampling_kwargs,
            )
            async for chunk in stream:
                ch_list = getattr(chunk, "choices", None) or []
                if not ch_list:
                    continue
                delta_obj = getattr(ch_list[0], "delta", None)
                delta = getattr(delta_obj, "content", None) if delta_obj is not None else None
                if delta:
                    output_chunks.append(delta)
                    yield delta
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context={**(context or {}), "task": task, "sampling": sampling_kwargs},
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="ok",
                prompt_text=f"{system}\n{prompt}",
                completion_text="".join(output_chunks),
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "stream": True,
                    **sampling_kwargs,
                },
                output_payload={"text": "".join(output_chunks)},
                db=self._db,
            )
        except Exception as e:
            log_llm_call(
                mode=self.profile,
                model=self.model,
                llm_endpoint=f"{self.base_url.rstrip('/')}/chat/completions",
                context={**(context or {}), "task": task, "sampling": sampling_kwargs},
                duration_ms=int((time.perf_counter() - start) * 1000),
                status="error",
                prompt_text=f"{system}\n{prompt}",
                completion_text="".join(output_chunks),
                error=str(e),
                input_payload={
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": max_tokens,
                    "stream": True,
                    **sampling_kwargs,
                },
                output_payload={"text": "".join(output_chunks)},
                db=self._db,
            )
            raise
