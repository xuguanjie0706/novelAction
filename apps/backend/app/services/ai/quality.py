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
from app.services.bootstrap.parse import parse_json
from app.utils.chapter_manuscript import split_plain_manuscript_and_index_block


class QualityMixin:
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
        memory_count = 120
        setting_count = 80
        character_count = 80
        storyline_count = 40
        power_count = 20

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
        chapter_label = "完整正文"

        system = """你是专业的网络小说编辑，负责对章节内容进行质量检查。
请严格按照 JSON 格式返回结果，不要有任何额外文字。

特别关注以下一致性问题：
1. 人物使用了超出其当前境界的技能/能力
2. 人物出现在与记录不符的位置
3. 已死亡/封印的人物突然出现
4. 人物行为违背其价值观和动机
5. 使用了尚未习得的技能或尚未获得的道具"""

        # 根据传入数据决定是否追加专属维度说明，避免 AI 对空数据做无效评分
        _extra_dim_doc = ""
        has_weave_hint = storylines_context and any(
            "故事线织网" in (s or "") for s in storylines_context
        )
        if storylines_context:
            _extra_dim_doc += (
                '\n    "storyline_progress": {{"score": 8, "status": "pass",'
                ' "comment": "本章推进了哪条故事线？有无与故事线状态矛盾的情节？（当前活跃故事线与本章内容的匹配度，0-10）"}},'
            )
        if has_weave_hint:
            _extra_dim_doc += (
                '\n    "storyline_beat_match": {{"score": 8, "status": "pass",'
                ' "comment": "本章实际推进是否兑现了织网中的计划节拍？（0-10）"}},'
                '\n    "storyline_tension_fit": {{"score": 8, "status": "pass",'
                ' "comment": "情节张力是否与计划张力曲线一致（±30 为合格）？（0-10）"}},'
                '\n    "storyline_screen_balance": {{"score": 8, "status": "pass",'
                ' "comment": "各故事线戏份是否与 weight 预算大致匹配？（0-10）"}},'
            )
        if power_systems_summary:
            _extra_dim_doc += (
                '\n    "realm_check": {{"score": 9, "status": "pass",'
                ' "comment": "本章功法/技能/战力描写是否符合境界体系规则？有无超纲行为（如低境界人物秒杀高境界）？（0-10）"}},'
            )

        _extra_constraints = ""
        if storylines_context:
            _extra_constraints += (
                "\n- storyline_progress < 6 时，issues 中必须加一条 type=\"storyline_neglect\" 的 warning，"
                "指出哪条活跃故事线被本章完全忽略或与状态矛盾"
            )
        if has_weave_hint:
            _extra_constraints += (
                "\n- storyline_beat_match < 6 时，issues 须加 type=\"storyline_drift\" 的 warning"
                "\n- storyline_tension_fit < 6 时，issues 须说明哪条线张力偏离计划"
            )
        if power_systems_summary:
            _extra_constraints += (
                "\n- realm_check < 6 时，issues 中必须加一条 type=\"realm_violation\" 的 warning，"
                "明确指出是哪个角色、在哪个场景、用了什么超出境界的能力"
            )

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
    "setting_consistency": {{"score": 7, "status": "warning", "comment": "人物位置/状态/持有物是否前后一致"}},
    "pacing": {{"score": 8, "status": "pass", "comment": "节奏是否合适"}},
    "hooks": {{"score": 9, "status": "excellent", "comment": "钩子和悬念是否到位"}},
    "outline_alignment": {{"score": 8, "status": "pass", "comment": "本章内容与大纲节点目标的匹配度"}},
    "face_slap_payoff": {{"score": 8, "status": "pass", "comment": "本章是否兑现之前积累的打脸/爽感期待？憋了几章的情绪有没有具体释放？（0-10）"}},
    "emotional_resonance": {{"score": 7, "status": "pass", "comment": "读者是否会为主角揪心/爽/心疼/愤怒？情感有没有被具体调动？（0-10）"}},
    "subscribe_intent": {{"score": 8, "status": "pass", "comment": "章末付费订阅下一章的意愿估分——读完最后一句会不会忍不住翻页？7分以上合格（0-10）"}}{_extra_dim_doc}
  }},
  "issues": [{{"type": "warning", "description": "具体问题描述，如：林默在第X章记录位置为青云城，本章却出现在远水城"}}],
  "suggestions": ["具体可操作的修改建议"],
  "summary": "整体评价一句话",
  "highlight_quote": "本章最有截图价值的1句原文（狠话/反转/让人背脊发凉的细节）；全章无亮句则填空字符串"
}}

评分额外约束：
- face_slap_payoff < 6 时，suggestions 必须包含一条"本章如何增加打脸兑现感"的具体操作
- subscribe_intent < 7 时，issues 中必须加一条 type="low_hook" 的 warning，说明章末钩子哪里不够抓人{_extra_constraints}
- 评分时先用编辑视角检查技术质量，再切换成「下班后刷手机的28岁读者」视角问：这章会让他熬夜追下一章吗？"""

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
            data = parse_json(response)
            if not isinstance(data, dict):
                raise ValueError("quality_check response is not a JSON object")
            if data.get("suggestions") is None:
                data["suggestions"] = []
            if data.get("issues") is None:
                data["issues"] = []
            if data.get("dimensions") is None:
                data["dimensions"] = {}
            return data
        except Exception as exc:
            logger.warning("quality_check JSON parse failed: %s", exc)
            return {
                "overall_score": 0,
                "dimensions": {},
                "issues": [],
                "suggestions": [],
                "summary": "质检结果解析失败，请重试",
                "raw_response": response,
                "error": "Failed to parse AI response",
            }

    def _micro_patch_narrative_window(self, body: str) -> str:
        """长章正文窗口：尽量给足完整叙事供局部替换定位。"""
        return self._clip_context(body, 800, 120000)

    async def quality_micro_patch(
        self,
        narrative_body: str,
        chapter_title: str,
        problem_summary: str,
        fix_direction: str,
        author_notes: str = "",
        *,
        operation: str = "quality_micro_patch",
    ) -> dict:
        """
        根据问题摘要与修正方向，让模型给出「原文连续摘录 → 替换文」；
        由路由在**完整叙事正文**上校验唯一匹配后做字符串级替换。
        """
        window = self._micro_patch_narrative_window(narrative_body)
        sf = (fix_direction or "").strip()
        an = (author_notes or "").strip()
        system = "你是网络小说正文编辑，只输出可机读的局部替换 JSON，不要任何多余文字。"
        prompt = f"""章节标题：{chapter_title}
全章叙事正文长度：{len(narrative_body)} 字（以下为正文窗口，可能含「中略」省略标记）

【正文窗口】
{window}

【待修正的问题】
{problem_summary}

【建议修正方向】
{sf or "（未给出；请结合问题自行给出最小改写）"}

【作者备注】
{an or "（无）"}

规则：
1. 找出与上述问题直接相关、且必须修改才能落实建议的**最小连续片段**（可含换行；从窗口中肉眼可抄录）。
2. `original_excerpt` 必须从上面【正文窗口】里**原样复制**（勿改写标点），长度约 15～500 字为宜。
3. 该片段在**整章完整叙事正文**（不仅是窗口）中应**恰好出现 1 次**。若你判断会出现多次、或需改多处、或窗口中无法定位，则将 original_excerpt、replacement_excerpt 都设为 ""，并在 rationale 写明原因（如 duplicate_span / need_multi_edit / need_tail）。
4. `replacement_excerpt` 为替换后的文字，人称/时态/语体与上下文一致；禁止借机扩写无关新剧情。

仅输出一个 JSON 对象：
{{
  "original_excerpt": "",
  "replacement_excerpt": "",
  "rationale": ""
}}"""
        try:
            response = await self._call_ai(
                system,
                prompt,
                max_tokens=max_tokens_quality_micro_patch(),
                context={"operation": operation, "chapter_title": chapter_title},
                task="quality.micro_patch",
            )
        except Exception as e:
            return {
                "error": str(e),
                "original_excerpt": "",
                "replacement_excerpt": "",
                "rationale": "upstream_error",
            }
        try:
            text = response.strip()
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
            if "```" in text:
                fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
                if fence:
                    text = fence.group(1).strip()
            start = text.find("{")
            if start != -1:
                text = text[start:]
            data = json.loads(text)
            return {
                "original_excerpt": str(data.get("original_excerpt") or "").strip(),
                "replacement_excerpt": str(data.get("replacement_excerpt") or "").strip(),
                "rationale": str(data.get("rationale") or "").strip(),
            }
        except Exception as e:
            return {
                "error": str(e),
                "original_excerpt": "",
                "replacement_excerpt": "",
                "rationale": "parse_error",
                "raw": response[:800] if isinstance(response, str) else "",
            }

    async def quality_debt_micro_patch(
        self,
        narrative_body: str,
        chapter_title: str,
        debt_summary: str,
        suggested_fix: str,
        author_notes: str,
    ) -> dict:
        """质量债务台账条目对应的局部微调（兼容旧调用名）。"""
        return await self.quality_micro_patch(
            narrative_body,
            chapter_title,
            debt_summary,
            suggested_fix,
            author_notes,
            operation="quality_debt_micro_patch",
        )

    async def quality_report_micro_patch(
        self,
        narrative_body: str,
        chapter_title: str,
        problem_summary: str,
        fix_direction: str,
        author_notes: str = "",
    ) -> dict:
        """章节质检报告优化建议对应的局部微调。"""
        return await self.quality_micro_patch(
            narrative_body,
            chapter_title,
            problem_summary,
            fix_direction,
            author_notes,
            operation="quality_check_micro_patch",
        )

    # ── 多章节连贯性检测 ────────────────────────────────
