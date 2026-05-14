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

from app.services.ai.guardrails import genre_guardrail_text


class OutlineMixin:
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
        protagonist_psychology: str = "",            # 主角心理档案（core_wound/current_desire/biggest_lie）
        villain_timelines: list[str] | None = None,  # 反派势力行动时间线摘要（来自 Faction.extra.villain_timeline）
        opening_contract: dict | None = None,        # 开局承诺清单（来自 Project.extra.opening_contract，仅第一卷前10章使用）
    ) -> dict:
        """为选定的大纲节点（卷或旧篇）生成详细的子章节计划。

        章节设计遵循「欲望→障碍→选择→代价」因果链：每章存在的理由是
        上一章选择的代价；每章的核心事件是本章选择的直接后果。

        Returns:
            包含 volume_analysis 和 chapters 数组的 dict；解析失败返回 {"error": ...}。
        """
        system = """你是拥有30年经验的网络小说策划，深刻理解网文追读机制。
你深知：章节的核心不是「发生了什么」，而是「主角主动想要什么→什么挡住了他→
他做了什么选择（选择暴露性格）→选择的代价喂给了下一章」。
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
        protagonist_psychology_context = (
            f"\n【主角心理档案（章节行为的底层驱动，高优先级约束）】\n{protagonist_psychology}\n"
            if protagonist_psychology else ""
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

        # ── 反派行动时间线注入 ───────────────────────────────
        villain_block = ""
        if villain_timelines:
            vt_lines = "\n".join(f"- {vt}" for vt in villain_timelines)
            villain_block = (
                f"\n【反派行动时间线（必须体现在章纲中）】\n"
                f"以下是主要反派势力的独立行动计划（不以主角为中心，而是他们主动推进的阴谋）：\n"
                f"{vt_lines}\n"
                f"要求：本卷章纲中必须至少有1章体现「反派主动行动」而非被动应付主角；\n"
                f"并在 core_event 中说明反派此时正在做什么（即便本章主视角是主角）。\n"
            )

        # ── 开局三章生死线（仅第一卷前三章触发）────────────────
        opening_death_line_block = ""
        is_opening_vol = existing_chapters == 0  # 第一卷第一批
        if is_opening_vol and opening_contract and isinstance(opening_contract, dict):
            ch1_hook = opening_contract.get("chapter1_hook", "")
            ch3_payoff = opening_contract.get("chapter3_payoff", "")
            first_200 = opening_contract.get("first_200_words_test", "")
            rhythm = opening_contract.get("chapter_rhythm", "")
            traps = opening_contract.get("opening_traps_to_avoid", [])
            traps_str = "；".join(traps) if isinstance(traps, list) else str(traps)
            opening_death_line_block = (
                f"\n【⚠️开局三章生死线 — 此卷前三章必须满足以下所有条件，否则读者无法追下去】\n"
                f"第1章前200字必须完成：{first_200 or '落地世界观、主角核心痛点、一个悬而未决的问题'}\n"
                f"第1章末钩子承诺：{ch1_hook or '读者必须知道答案才肯看第2章的问题'}\n"
                f"第3章小爽点：{ch3_payoff or '主角的第一次具体反转或胜利'}\n"
                f"前10章节奏：{rhythm or '（未设定，请自行规划快慢节奏）'}\n"
                f"必须避免的开局坑：{traps_str or '（未设定）'}\n"
                f"生死线约束：前三章的 opening_hook 必须紧贴以上要求，不能使用通用模板钩子。\n"
            )

        prompt = f"""小说：《{project_title}》（{genre}）
当前节点：{node_type == 'volume' and '卷' or '旧篇'}《{node_title}》
节点概述：{node_summary or '（未填写）'}

世界观摘要：{world_summary[:400]}
主要人物（主线核心卡司，非全书全部人物——配角可按剧情需要随时引入）：{character_summary[:500]}
全书立意：{theme_statement[:300] or '（未填写；请从创意和人物中提炼一条贯穿全书的价值命题）'}
{realm_constraint_block}{protagonist_state_context}{protagonist_psychology_context}{global_context}{prior_plot_block}{prior_ledger_block}{previous_context}{continuity_context}{batch_goal_context}{villain_block}{opening_death_line_block}
请为本{node_type == 'volume' and '卷' or '旧篇'}生成 {chapter_count} 个章节计划，章节编号从第{start_num}章开始。
{genre_guardrail_text(genre)}

每章使用「欲望-障碍-选择-代价」因果链格式，返回 JSON：
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
      "protagonist_want": "主角这一章主动想要什么（必须是主动欲望，不是「被逼应付」）",
      "protagonist_obstacle": "什么具体阻止了他（内部恐惧或外部冲突，不能只写「敌人」）",
      "protagonist_choice": "他做了什么关键选择（这个选择必须暴露性格，而不只是解决问题）",
      "choice_cost": "这个选择的代价（喂给下一章的债务，不能零代价）",
      "opening_hook": "开篇钩子：前500字的核心手段。例：用主角被宣判死刑的场面倒叙开篇",
      "core_event": "核心事件：必须是 protagonist_choice 的直接后果，格式「因[choice]→[result]」",
      "character_change": "人物变化：谁的认知/处境/关系发生了不可逆变化",
      "foreshadow": "伏笔管理：埋[伏笔内容|主题:与立意的关联] 收[伏笔内容]（无则填空）",
      "villain_action": "反派这一章在做什么（即便不是本章视角），以及如何逼迫主角",
      "end_hook": "章末钩子：读者读完最后一句停不下来的原因，要具体到手法",
      "reader_emotion_target": "本章结束时读者的目标情绪（exciting/tense/sad/romantic/mysterious/warm/anxious/epic）",
      "pacing": "fast/medium/slow",
      "word_estimate": 2300
    }}
  ]
}}

重点要求：
1. core_event 必须是 protagonist_choice 的直接后果，不能与 choice 在逻辑上无关
2. choice_cost 不能为空——零代价的选择不是戏剧，必须为下一章留下债务
3. villain_action 不能只写"（无）"——反派在大格局中始终有独立行动
4. 每章「章末钩子」必须具体，不能只写"留下悬念"，要说清楚「悬念的具体内容」
5. 每章字数预估控制在 2200-2400 字，默认 2300 字
6. 伏笔要有连续性，本卷内至少有2条贯穿始终的伏笔线；埋入时附「|主题:xxx」说明与立意的关联
7. 如果提供了已生成章节上下文或滚动连续性账本，必须承接上一批章末钩子、人物状态和未回收伏笔，不得重复已发生的核心事件
8. 本批第一章要自然回应上一批最后一章留下的具体悬念；如果处于新卷开头，则先承接全书卷线蓝图再开启本卷核心问题
9. 若提供了「前几卷已规划章纲」：不得复述或改头换面重复前序已写核心事件；新卷情节在其上推进
10. 若提供了「前几卷伏笔台账」：本卷各章 foreshadow 字段须点名埋/收，优先处理台账中高优先级仍未回收条目，并与章纲五要素一致
11. 「合同型伏笔」硬约束：台账中 deadline_chapter <= 本批最后一章章号 的条目视为「逾期伏笔」，必须在本批章纲中安排至少一章写明「收[F-xxx：...]」，否则视为结构缺陷"""

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
        overdue_foreshadow_ledger: str = "",  # 逾期未回收伏笔清单（F-编号:描述:deadline_chapter）
    ) -> dict:
        """
        大纲质检：检查卷内/全书章节计划的连续性，并返回可定位、可修复的问题列表。
        """
        chapter_lines = []
        for ch in chapters:
            # 拼装行时，若新字段（因果链）存在则带入，让质检看到完整上下文
            parts = [
                f"第{ch.get('number', '?')}章：{ch.get('title', '未命名')}",
                f"核心事件：{ch.get('core_event', '')}",
                f"人物变化：{ch.get('character_change', '')}",
                f"伏笔：{ch.get('foreshadow', '')}",
                f"章末钩子：{ch.get('end_hook', '')}",
            ]
            # 因果链字段（新大纲有，旧大纲为空——空时不拼，避免噪音）
            choice = (ch.get("protagonist_choice") or "").strip()
            cost = (ch.get("choice_cost") or "").strip()
            if choice:
                parts.append(f"主角选择：{choice}")
            if cost:
                parts.append(f"选择代价：{cost}")
            chapter_lines.append(" | ".join(parts))

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

{("【⚠️逾期未回收伏笔清单（必须在本批章纲中安排回收）】" + chr(10) + self._clip_context(overdue_foreshadow_ledger, 2000, None, field_name="overdue_foreshadow")) if overdue_foreshadow_ledger else ""}

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
9. 逾期伏笔：若提供了「逾期未回收伏笔清单」，检查本批章纲是否有对应章安排回收；未安排者报告 overdue_foreshadow 类型问题

返回JSON：
{{
  "scope": "{scope}",
  "overall_score": 0,
  "status": "pass/warning/fail",
  "summary": "一句话总结",
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "type": "continuity/duplicate_event/hook_continuity/foreshadow/overdue_foreshadow/character_arc/pacing/theme_alignment",
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

