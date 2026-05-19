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


class WritingToolsMixin:
    async def pre_write_warning(
        self,
        project_title: str,
        genre: str,
        chapter_plan_summary: str,          # 本章计划摘要（五要素或简述）
        memory_chunks: list[dict],           # MemoryChunk 列表，每条含 title/content/memory_type
        continuity_state: str = "",          # 滚动连续性账本
        foreshadow_ledger: str = "",         # 伏笔台账
        character_states: str = "",          # 主要角色当前状态快照
        power_systems_summary: str = "",     # 境界体系摘要（含各阶名称与规则）
        outline_context: str = "",           # 本章大纲五要素（hook/summary/conflict/highlight/milestone）
        phase: str = "",                     # 章节所在阶段（opening/rising/turning/dark_hour/climax/ending）
    ) -> dict:
        """
        写前预警：像一位有30年经验的网文主编，在落笔前把本章的「坑、约束、写法」全交代清楚。

        不仅排雷（连续性/伏笔/设定/OOC/节奏），还输出：
        - protagonist_fact_sheet：主角此刻的精确状态锁定（境界/位置/技能/道具），防止幻觉
        - writing_brief：本章应该怎么写（开篇策略/冲突结构/章末钩子）
        - must_events：本章必须发生的事件（剧情硬约束）
        - hallucination_traps：写这类章节时 AI 最容易犯的错误清单

        Returns:
            dict with keys: ok, risk_count, risks, reminders,
                            protagonist_fact_sheet, writing_brief,
                            must_events, hallucination_traps
        """
        # 拼接记忆摘要，按类型分组
        mem_lines: list[str] = []
        for chunk in memory_chunks[:40]:
            mt = chunk.get("memory_type", "event")
            title = (chunk.get("title") or "").strip()
            content = (chunk.get("content") or "").strip()[:200]
            mem_lines.append(f"[{mt}] {title}：{content}")
        mem_block = "\n".join(mem_lines) if mem_lines else "（无记忆条目）"

        phase_hint = {
            "opening":   "开局期：爽点密集，钩子3章一次，字数偏短，不要铺垫过重",
            "rising":    "起飞期：势力扩张，感情线接入，可以开始拉长单章字数",
            "turning":   "转折期：矛盾升级，代价兑现，节奏可稍微放缓以铺陈",
            "dark_hour": "至暗期：允许「虐」，允许主角吃亏，节奏放慢，心理戏加重",
            "climax":    "高潮期：伏笔回收，爆点拉满，爽感最大化，章末钩子必须炸裂",
            "ending":    "收束期：留悬念种子，给读者追读下一卷的理由",
        }.get((phase or "").lower().strip(), "")

        system = (
            "你是拥有三十年经验的网络小说主编，精通玄幻、修仙、都市等各类型。"
            "你的职责是在作者落笔前，像老编辑审稿一样，把这一章的「坑、约束、写法」全部交代清楚，"
            "让写正文的 AI 无法出现幻觉和逻辑错误。严格返回 JSON，不要任何额外文字。"
        )

        prompt = f"""小说：《{project_title}》（{genre}）
{f'当前阶段：{phase_hint}' if phase_hint else ''}

══════════════════════════════════════
【本章计划（大纲五要素）】
{self._clip_context(outline_context or chapter_plan_summary, 1500, None, field_name="outline")}

══════════════════════════════════════
【主要角色当前状态（精确到境界/位置/技能/持有物）】
{self._clip_context(character_states, 1200, None, field_name="char_states") or "（未提供）"}

【境界体系规则（防止境界幻觉）】
{self._clip_context(power_systems_summary, 800, None, field_name="power_systems") or "（未提供）"}

【滚动连续性账本（最近章节状态）】
{self._clip_context(continuity_state, 2000, None, field_name="continuity") or "（未提供）"}

【伏笔台账（含未收束条目与逾期警告）】
{self._clip_context(foreshadow_ledger, 1500, None, field_name="foreshadow_ledger") or "（无伏笔记录）"}

【历史记忆库（事件/状态/冲突）】
{self._clip_context(mem_block, 2500, None, field_name="memory_chunks")}

══════════════════════════════════════
请以「三十年主编」的视角完成以下四件事，**全部输出到 JSON**：

① 主角状态锁定（protagonist_fact_sheet）
   核对上述资料，锁定本章开笔时主角的精确状态，AI 写正文必须严格遵守这份清单：
   - realm：当前境界名称（精确，不可升级或缩写）
   - location：当前所在位置
   - key_skills：本章可以合理使用的技能/功法（各1句话说明来源）
   - key_items：当前持有的关键道具/法宝（各1句话）
   - forbidden：本章绝对不能出现的能力/道具/状态（还未习得/已损毁/不在身边）

② 本章写作简报（writing_brief）
   给写章 AI 的具体写法指导，像导演给演员的场景说明：
   - opening_strategy：开篇第一段应该怎么切入（人物/动作/对话/环境？为什么？）
   - conflict_structure：本章冲突如何分层递进（给出2-3个节拍）
   - closing_hook：最后一段的钩子设计（悬念/爽感/伏笔引爆？具体怎么收？）
   - word_rhythm：字数与节奏建议（哪些场景应该详写/略写）

③ 本章必发事件（must_events）
   根据大纲计划，列出本章必须在正文中落地的关键事件（2-4条，每条一句话）。
   不在大纲里但记忆库/伏笔台账要求必须处理的，也列进来。

④ 幻觉预防清单（hallucination_traps）
   针对这一章的具体内容，列出写 AI 最容易犯的错误（3-5条），格式：「陷阱描述 → 正确做法」

⑤ 风险扫描（risks）
   逐条对照资料，发现以下类型的潜在问题：
   - continuity：连续性矛盾（人物状态/位置/事件顺序）
   - foreshadow：伏笔违约（漏收/误收）
   - setting：设定违规（境界/势力/道具与世界观矛盾）
   - ooc：人物OOC（行为与性格/价值观/创伤明显冲突）
   - pacing：节奏预警（与前章钩子期望落差）

返回 JSON（所有字段必须存在，无内容填空数组/空字符串）：
{{
  "ok": true,
  "risk_count": 0,
  "protagonist_fact_sheet": {{
    "realm": "精确境界名",
    "location": "当前位置",
    "key_skills": ["技能A（来源/原因）", "技能B（来源/原因）"],
    "key_items": ["道具A（来源/当前状态）"],
    "forbidden": ["不能使用X（原因）", "不能出现Y（原因）"]
  }},
  "writing_brief": {{
    "opening_strategy": "具体的开篇切入建议，一到两句话",
    "conflict_structure": "节拍1 → 节拍2 → 节拍3（每个节拍一句话描述）",
    "closing_hook": "章末钩子的具体设计，一到两句话",
    "word_rhythm": "哪段详写、哪段略写的建议"
  }},
  "must_events": [
    "本章必须发生的事件1",
    "本章必须发生的事件2"
  ],
  "hallucination_traps": [
    "陷阱：AI 容易写出X → 正确做法：应该Y",
    "陷阱：AI 容易忽略Z → 正确做法：需要W"
  ],
  "risks": [
    {{
      "type": "continuity/foreshadow/setting/ooc/pacing",
      "severity": "low/medium/high/critical",
      "description": "具体矛盾点，精确到涉及条目和章节",
      "suggested_fix": "建议解决方案"
    }}
  ],
  "reminders": [
    "一句话写作提醒（如：本章主角境界是X，不能使用Y技能）"
  ]
}}
若无风险则 risks 为空数组，ok=true；有 high/critical 风险则 ok=false。"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=2500,
            context={"operation": "pre_write_warning", "chapter_plan": chapter_plan_summary[:80]},
            task="quality.check",
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
                raise ValueError("No JSON found")
            data = json.loads(text[start:])
            risks = [r for r in (data.get("risks") or []) if isinstance(r, dict) and r.get("description")]
            reminders = [str(r) for r in (data.get("reminders") or []) if r]
            has_critical = any(r.get("severity") in ("high", "critical") for r in risks)

            # 提取新增字段，做基础类型保护
            def _str(v, fallback="") -> str:
                return str(v).strip() if v else fallback

            def _strlist(v) -> list[str]:
                if isinstance(v, list):
                    return [str(x).strip() for x in v if x]
                return []

            protagonist_fact_sheet = data.get("protagonist_fact_sheet") or {}
            if not isinstance(protagonist_fact_sheet, dict):
                protagonist_fact_sheet = {}

            writing_brief_raw = data.get("writing_brief") or {}
            if not isinstance(writing_brief_raw, dict):
                writing_brief_raw = {}
            writing_brief = {
                "opening_strategy": _str(writing_brief_raw.get("opening_strategy")),
                "conflict_structure": _str(writing_brief_raw.get("conflict_structure")),
                "closing_hook": _str(writing_brief_raw.get("closing_hook")),
                "word_rhythm": _str(writing_brief_raw.get("word_rhythm")),
            }

            return {
                "ok": not has_critical,
                "risk_count": len(risks),
                "protagonist_fact_sheet": {
                    "realm": _str(protagonist_fact_sheet.get("realm")),
                    "location": _str(protagonist_fact_sheet.get("location")),
                    "key_skills": _strlist(protagonist_fact_sheet.get("key_skills")),
                    "key_items": _strlist(protagonist_fact_sheet.get("key_items")),
                    "forbidden": _strlist(protagonist_fact_sheet.get("forbidden")),
                },
                "writing_brief": writing_brief,
                "must_events": _strlist(data.get("must_events")),
                "hallucination_traps": _strlist(data.get("hallucination_traps")),
                "risks": risks[:15],
                "reminders": reminders[:10],
            }
        except Exception as e:
            return {
                "ok": True, "risk_count": 0,
                "protagonist_fact_sheet": {"realm": "", "location": "", "key_skills": [], "key_items": [], "forbidden": []},
                "writing_brief": {"opening_strategy": "", "conflict_structure": "", "closing_hook": "", "word_rhythm": ""},
                "must_events": [], "hallucination_traps": [],
                "risks": [], "reminders": [],
                "error": str(e), "raw": response[:300],
            }

    # ── 三层调度：章纲 → 分场（Scene Plan）─────────────────────────────────
    async def scene_plan(
        self,
        chapter_title: str,
        chapter_summary: str,
        genre: str = "",
        positioning: Optional[dict] = None,
        existing_characters: List[dict] = None,
        prev_directives: str = "",
        model_profile: str = "local",
        word_target: int = 2200,
        character_states: Optional[List[dict]] = None,
        open_foreshadows: Optional[List[dict]] = None,
        open_reader_promises: Optional[List[dict]] = None,
    ) -> dict:
        """
        根据章纲生成结构化分场计划（4-8 场）。

        每场包含：POV、时间、地点、在场角色、目标、冲突、转折、钩子、字数预算、感官焦点、节奏。

        Args:
            chapter_title: 章节标题。
            chapter_summary: 章节摘要（≤800 字）。
            genre: 类型标签，用于 genre_kit guardrail。
            positioning: 立项定位 dict（取 selling_point/taboo_lines）。
            existing_characters: 角色列表 [{"id":..., "name":...}]，仅用于 prompt 展示；
                                 POV 解析依赖调用方的 char_map。
            prev_directives: 上一章复盘指令（最高优先级约束）。
            model_profile: "local" / "gemini"。
            word_target: 全章目标字数，分配各场预算基准。
            character_states: 关键角色当前状态列表，每条含 name/current_realm/
                              current_status/current_location（可选字段）。有数据时注入约束块。
            open_foreshadows: 未闭合伏笔列表，每条含 title/description/priority。
                              高优先级（priority≥4）在场景安排时需有意识回收或推进。
            open_reader_promises: 未兑现读者承诺列表，每条含 promise_text/promise_type/priority。
                                  高优先级在本章分场中必须有至少一场回应或推进。
        """
        system = (
            "你是资深网文分镜师。严格返回 JSON，不要任何额外文字。"
            "必须严格遵守 genre_kit 的 pacing_guide 和 side_character_quota。"
            "每章 4-8 场，字数总和接近 word_target。"
            "每场必须有明确的 POV（禁止全知），在场角色不得超过 genre_kit quota。"
        )

        kit_block = ""
        if genre:
            from app.services.genre_kit import get_genre_guardrail
            kit_block = "\n" + get_genre_guardrail(genre) + "\n"

        positioning_block = ""
        if positioning:
            positioning_block = "\n【立项定位】\n" + json.dumps(positioning, ensure_ascii=False) + "\n"

        prev_block = ""
        if prev_directives.strip():
            prev_block = "\n【上一章复盘指令（最高优先级）】\n" + prev_directives.strip() + "\n"

        char_block = ""
        if existing_characters:
            char_lines = [f"- {c.get('name','')}（id:{c.get('id','')}）" for c in existing_characters[:8]]
            char_block = "\n当前主要角色：\n" + "\n".join(char_lines)

        # ── 约束注入块（仅有数据时才出现）──────────────────────
        state_block = ""
        if character_states:
            lines = []
            for cs in character_states[:6]:
                parts = [cs.get("name", "?")]
                if cs.get("current_realm"):
                    parts.append(f"境界:{cs['current_realm']}")
                if cs.get("current_status") and cs["current_status"] != "alive":
                    parts.append(f"状态:{cs['current_status']}")
                if cs.get("current_location"):
                    parts.append(f"位置:{cs['current_location']}")
                lines.append("  " + " | ".join(parts))
            state_block = "\n【当前角色状态（分场须保持一致）】\n" + "\n".join(lines) + "\n"

        foreshadow_block = ""
        if open_foreshadows:
            # 按优先级降序，优先展示高权重伏笔
            sorted_fw = sorted(open_foreshadows, key=lambda x: -(x.get("priority") or 3))
            lines = []
            for fw in sorted_fw[:4]:
                pri = fw.get("priority") or 3
                marker = "⚡" if pri >= 4 else "·"
                desc = (fw.get("description") or "")[:60]
                lines.append(f"  {marker} {fw.get('title','?')}：{desc}")
            foreshadow_block = (
                "\n【未闭合伏笔（⚡=高优先，本章宜推进或回收）】\n"
                + "\n".join(lines) + "\n"
            )

        promise_block = ""
        if open_reader_promises:
            sorted_rp = sorted(open_reader_promises, key=lambda x: -(x.get("priority") or 3))
            lines = []
            for rp in sorted_rp[:3]:
                pri = rp.get("priority") or 3
                marker = "⚡" if pri >= 4 else "·"
                ptype = rp.get("promise_type") or ""
                text = (rp.get("promise_text") or "")[:80]
                lines.append(f"  {marker} [{ptype}] {text}")
            promise_block = (
                "\n【未兑现读者承诺（⚡=高优先，本章至少一场须回应或推进）】\n"
                + "\n".join(lines) + "\n"
            )

        prompt = f"""{kit_block}{positioning_block}{prev_block}{state_block}{foreshadow_block}{promise_block}
本章标题：《{chapter_title}》
本章摘要：{chapter_summary[:800]}
{char_block}

请为本章拆分 4-8 场（scene），返回 JSON：
{{
  "scenes": [
    {{
      "order": 1,
      "title": "场标题",
      "time": "第X日·夜",
      "location_name": "地点",
      "pov_character_name": "POV 角色名（必须是现有角色之一）",
      "characters_on_stage": ["角色名列表"],
      "goal": "本场角色想要什么",
      "conflict": "冲突/障碍",
      "turn": "本场关键转折",
      "hook": "场末钩子（留给下一场）",
      "hook_strength": 3,
      "word_budget": 350,
      "pacing": "fast/mid/slow",
      "sensory_focus": "sight/sound/mixed"
    }}
  ],
  "total_word_budget": {word_target},
  "notes": "分场说明（可选）"
}}
只返回 JSON。"""

        raw = await self._call_with_retry(
            system,
            prompt,
            max_tokens=2000,
            task="draft.scene_plan",
        )
        try:
            data = _parse_json(raw)
        except Exception:
            # 兜底：返回最简 4 场
            data = {
                "scenes": [
                    {"order": 1, "title": "开场", "time": "同日", "location_name": "未知", "pov_character_name": (existing_characters[0]["name"] if existing_characters else "主角"), "characters_on_stage": [], "goal": chapter_summary[:60], "conflict": "", "turn": "", "hook": "章末钩子待定", "hook_strength": 3, "word_budget": 500, "pacing": "mid", "sensory_focus": "mixed"},
                    {"order": 2, "title": "冲突升级", "time": "同日", "location_name": "未知", "pov_character_name": (existing_characters[0]["name"] if existing_characters else "主角"), "characters_on_stage": [], "goal": "", "conflict": "", "turn": "", "hook": "", "hook_strength": 3, "word_budget": 500, "pacing": "mid", "sensory_focus": "mixed"},
                    {"order": 3, "title": "转折", "time": "同日", "location_name": "未知", "pov_character_name": (existing_characters[0]["name"] if existing_characters else "主角"), "characters_on_stage": [], "goal": "", "conflict": "", "turn": "", "hook": "", "hook_strength": 4, "word_budget": 600, "pacing": "fast", "sensory_focus": "mixed"},
                    {"order": 4, "title": "收束与钩子", "time": "同日", "location_name": "未知", "pov_character_name": (existing_characters[0]["name"] if existing_characters else "主角"), "characters_on_stage": [], "goal": "", "conflict": "", "turn": "", "hook": "下一章方向", "hook_strength": 5, "word_budget": 600, "pacing": "mid", "sensory_focus": "mixed"},
                ],
                "total_word_budget": word_target,
                "notes": "兜底分场（LLM 解析失败）"
            }
        return data

    # ── 读者心理模拟 ──────────────────────────────────
    async def reader_psychology_sim(
        self,
        project_title: str,
        genre: str,
        recent_chapters: list[dict],         # 最近10章的摘要，每条含 title/summary/hook_strength/subscribe_intent_score
        positioning: dict | None = None,     # Project.extra.positioning（目标读者画像、爽点类型等）
        current_chapter_number: int = 0,
    ) -> dict:
        """
        读者心理模拟：模拟目标读者阅读最近若干章后的感受，输出追读意愿评分和流失风险点。
        返回：{"read_through_score": 7, "dropout_risks": [...], "strengths": [...], "editor_verdict": "..."}
        """
        if not recent_chapters:
            return {"error": "no chapters provided"}

        # 拼接最近章节摘要
        ch_lines: list[str] = []
        for ch in recent_chapters[-10:]:
            num = ch.get("number") or ch.get("chapter_number") or "?"
            title = ch.get("title") or ""
            summary = (ch.get("summary") or "").strip()[:200]
            hook = ch.get("hook_strength", "?")
            sub_score = ch.get("subscribe_intent_score", "?")
            ch_lines.append(f"第{num}章《{title}》 钩子强度:{hook}/5 追读分:{sub_score}/10\n  {summary}")
        chapters_block = "\n".join(ch_lines)

        pos_block = ""
        if positioning and isinstance(positioning, dict):
            audience = positioning.get("target_audience", "")
            tropes = positioning.get("tropes", "")
            selling_point = positioning.get("selling_point", "")
            face_slap = positioning.get("face_slap_pattern", "")
            pos_block = (
                f"\n【目标读者画像与爽点设计】\n"
                f"目标受众：{audience}\n"
                f"核心爽点类型：{tropes}\n"
                f"卖点差异化：{selling_point}\n"
                f"打脸节奏：{face_slap}\n"
            )

        system = "你是专业的网络小说读者体验分析师，模拟目标读者视角进行追读意愿评估。严格返回JSON。"
        prompt = f"""小说：《{project_title}》（{genre}）
当前已写至第{current_chapter_number}章。
{pos_block}
【最近章节概览（模拟读者视角）】
{self._clip_context(chapters_block, 4000, None, field_name="recent_chapters")}

请以「目标读者」的视角，模拟读完以上章节后的真实感受，评估：

1. **追读意愿评分**（1-10）：读完最后一章后，有多大可能点「订阅」或「追更」
2. **流失风险点**：哪些章节/情节模式会让目标读者放弃（要具体，如：第X章节奏拖沓、第Y章爽点兑现不足）
3. **优势段落**：哪些地方做得好，读者会截图转发或催更
4. **编辑意见**：如果你是责任编辑，给作者最关键的3条建议

返回JSON：
{{
  "read_through_score": 7,
  "score_basis": "评分依据（一句话说明高/低的主要原因）",
  "trend": "rising/stable/declining",
  "trend_note": "追读趋势说明（如：连续3章钩子强度下降，进入衰减区）",
  "dropout_risks": [
    {{
      "chapter_range": "第X-Y章",
      "risk_type": "pacing/payoff/repetition/ooc/hook_weak/setting_inconsistency",
      "description": "具体流失原因",
      "severity": "low/medium/high"
    }}
  ],
  "strengths": ["做得好的具体点（章节级别）"],
  "editor_verdict": "责任编辑给作者的最关键建议（100字以内，直接、可执行）",
  "immediate_action": "下一章必须做的最重要一件事（一句话）"
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=1800,
            context={"operation": "reader_psychology_sim", "chapter": current_chapter_number},
            task="quality.check",
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
                raise ValueError("No JSON found")
            data = json.loads(text[start:])
            score = data.get("read_through_score", 5)
            try:
                score = max(1, min(10, int(score)))
            except Exception:
                score = 5
            return {
                "read_through_score": score,
                "score_basis": data.get("score_basis", ""),
                "trend": data.get("trend", "stable"),
                "trend_note": data.get("trend_note", ""),
                "dropout_risks": [r for r in (data.get("dropout_risks") or []) if isinstance(r, dict)][:10],
                "strengths": [s for s in (data.get("strengths") or []) if s][:8],
                "editor_verdict": data.get("editor_verdict", ""),
                "immediate_action": data.get("immediate_action", ""),
            }
        except Exception as e:
            return {"error": str(e), "raw": response[:300]}

