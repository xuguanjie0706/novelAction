"""
outline_ai_quality.py — 大纲质检与修复 Mixin

职责：
  OutlineQualityMixin.outline_quality_check → 检查章节计划的连续性，返回可定位问题列表
  OutlineQualityMixin.outline_repair_plan   → 生成大纲修复补丁计划
  OutlineQualityMixin._ISSUE_TYPE_REPAIR_HINTS → 问题类型→差异化修复指引映射
  OutlineQualityMixin._build_issue_type_hints  → 从质检报告提取问题类型生成指引文本
"""
from __future__ import annotations

import json
import logging
import re

from app.services.llm_token_budgets import max_tokens_outline_quality_check

logger = logging.getLogger(__name__)


class OutlineQualityMixin:
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
        positioning_context: str = "",         # 立项定位 + 开局承诺（防漂移核心锚点）
    ) -> dict:
        """大纲质检：检查卷内/全书章节计划的连续性，返回可定位、可修复的问题列表。

        positioning_context 是防止质检「漂移」的核心约束块——AI 应对照商业定位
        （目标读者、爽点节奏、打脸节奏、禁忌红线）而非通用文学标准打分。

        Args:
            positioning_context: _format_positioning_context() 的输出；空时不影响原有行为。
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

        # positioning 块：有则插入，没有不影响原有提示词结构
        positioning_block = (
            f"\n{self._clip_context(positioning_context, 1400, None, field_name='positioning')}\n"
            if positioning_context else ""
        )

        system = "你是资深长篇网文主编，专门做大纲质检和结构化修订建议。严格返回JSON，不要任何额外文字。"
        prompt = f"""小说：《{project_title}》（{genre}）
质检范围：{scope}
当前节点：{node_title}
节点概述：{node_summary or '（未填写）'}
全书立意：{theme_statement or '（未填写）'}
{positioning_block}
【故事圣经账本】
{self._clip_context(story_bible_context, 3200, None, field_name="story_bible") or '（未提供）'}

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

请检查（优先级从高到低）：
1. 定位兑现：每章核心事件是否符合立项定位的爽点节奏/打脸频率/禁忌红线；开局承诺是否按章兑现
2. 卷内连续性：章节因果是否断裂、是否重复同类事件、人物状态是否跳变
3. 跨卷承接：是否回应前卷/前批章末钩子，是否提前透支后续卷爆点
4. 伏笔：新埋/回收是否清楚，是否出现只埋不管、无来源回收、重复伏笔
5. 人物弧：人物选择、代价、关系变化是否逐步推进
6. 节奏与追读：开篇钩子、章末钩子、高潮分布是否支撑追读
7. 全书立意：核心事件是否服务主题，而不是单纯堆事件
8. 故事圣经一致性：角色死亡/封印/失踪后再登场必须有明确机制；核心道具、力量体系、势力目标、世界规则和人物弧线不得被后续章节随意否定
9. 篇幅兑现：检查当前大纲是否支撑目标字数，重点识别中后期节奏压缩（如跨位面速刷、关键成长阶段被跳过）
10. 逾期伏笔：若提供了「逾期未回收伏笔清单」，检查本批章纲是否有对应章安排回收；未安排者报告 overdue_foreshadow 类型问题

返回JSON：
{{
  "scope": "{scope}",
  "overall_score": 0,
  "status": "pass/warning/fail",
  "summary": "一句话总结",
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "type": "continuity/duplicate_event/hook_continuity/foreshadow/overdue_foreshadow/character_arc/pacing/theme_alignment/positioning_drift/reader_promise_breach",
      "chapter_numbers": [1],
      "description": "问题说明，要具体到章节和原因，并指出违反了哪条定位约束（如有）",
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

    # ── 问题类型 → 差异化修复指引映射 ──────────────────────────────────
    _ISSUE_TYPE_REPAIR_HINTS: dict[str, str] = {
        # 爽点/定位漂移
        "positioning_drift": (
            "⚑ 定位漂移：core_event 必须包含明确的爽点兑现动作（打脸/逆袭/碾压/出手即赢等），"
            "不得将爽点场景改成内省独白或铺垫说明。"
        ),
        "reader_promise_breach": (
            "⚑ 承诺未兑现：对应章节的 core_event 或 end_hook 必须明确兑现前章/卷末的读者承诺，"
            "如「主角展示新实力」「敌人落败」等具体行动，不可只写感悟或准备。"
        ),
        # 节奏
        "pacing_too_fast": (
            "⚑ 节奏过快：不得删减已有的过渡与代价章节；若要压缩，只能在不影响承载力的铺垫细节上做。"
            "必要时在 opening_hook 加入「上章余波/收尾」来还原节奏缓冲。"
        ),
        "pacing_too_slow": (
            "⚑ 节奏拖沓：core_event 需包含推动情节向前的具体冲突或突破，"
            "删去可直接跳过的过渡描写，但保留伏笔布设。"
        ),
        "pacing_problem": (
            "⚑ 节奏问题：优先调整 opening_hook 和 end_hook 的张力，"
            "增强开篇悬念或章末钩子，不要轻易改动 core_event 的主要事件。"
        ),
        # 钩子
        "hook_weak": (
            "⚑ 钩子弱：end_hook 必须提出一个具体的「未解决悬念」或「危机预告」，"
            "禁止用「主角若有所思」「准备下一步」等无张力结尾。"
        ),
        "chapter_hook_weak": (
            "⚑ 章末钩子弱：end_hook 需包含至少一个「读者不翻页会后悔」的信息缺口或紧迫感，"
            "如「意外出现的人物」「反转揭露」「紧迫计时」。"
        ),
        # 伏笔
        "foreshadow_breach": (
            "⚑ 伏笔断裂：修复 foreshadow 字段时，必须保证该伏笔与之前章节已埋设的内容一致，"
            "不能凭空新增未在前文出现过的道具/人物/规则。"
        ),
        "foreshadow_overdue": (
            "⚑ 伏笔逾期：该章节应回收之前埋下的伏笔，在 core_event 中安排伏笔兑现场景，"
            "而非继续延期或新增不相关伏笔。"
        ),
        # 人物/生死
        "death_continuity": (
            "⚑ 生死连续性：参见上方【生死修复硬约束】，务必同时提供死亡章和再现章的 patch，"
            "两处缺一不可，且严格遵守字符间距规则。"
        ),
        "character_death_continuity": (
            "⚑ 角色生死连续性：同上，严格按照硬约束修复，不要遗漏任何一个字段中的死亡词。"
        ),
        # 境界
        "realm_mismatch": (
            "⚑ 境界错误：只替换真正的境界名误用，复合动作词（如「炼化神火」「化神炉」）中的"
            "「化神」不是境界名，勿误改；替换后境界名必须来自白名单。"
        ),
        "realm_term_error": (
            "⚑ 修真术语误用：仅修改确认为传统修真境界名的词，其余保留原文。"
        ),
        # 结构
        "structure_gap": (
            "⚑ 结构缺口：chapter_change 需说明主角在该章的明确收获或损失，"
            "不能留白；收获/损失应与 core_event 逻辑一致。"
        ),
        "embedding_duplicate": (
            "⚑ 重复章节：该章 core_event 与邻近章节高度雷同，需调整为「差异化场景」，"
            "例如换一个冲突对象、换一种解决方式，或引入新的变量。"
        ),
    }

    @classmethod
    def _build_issue_type_hints(cls, quality_report: dict) -> str:
        """从质检报告提取问题类型，生成差异化修复指引文本。

        Args:
            quality_report: 质检报告 dict，含 issues 列表。

        Returns:
            若存在已知问题类型则返回格式化的指引段落，否则返回空字符串。
        """
        if not isinstance(quality_report, dict):
            return ""
        seen_types: set[str] = set()
        hints: list[str] = []
        for issue in quality_report.get("issues", []):
            if not isinstance(issue, dict):
                continue
            issue_type: str = issue.get("type", "")
            if issue_type and issue_type not in seen_types:
                hint = cls._ISSUE_TYPE_REPAIR_HINTS.get(issue_type)
                if hint:
                    hints.append(hint)
                    seen_types.add(issue_type)
        if not hints:
            return ""
        lines = "\n".join(f"  {h}" for h in hints)
        return f"\n【针对本次质检问题的专项修复要求】\n{lines}\n"

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
        realm_whitelist: list[str] | None = None,
        character_life_state_ledger: str = "",
        positioning_context: str = "",  # 立项定位 + 开局承诺；修复 patch 须符合商业定位要求
        linter_context: str = "",  # 章纲 linter 欠债块（volume.extra.linter_issues）
    ) -> dict:
        """生成大纲修复补丁计划。

        章节列表支持两类条目：
        - 普通章节（无 ``_context_only`` 字段）：质检标记的问题章节，AI 应输出 patch。
        - 上下文章节（``_context_only=True``）：问题章节的邻近章节，仅供 AI 理解前后文
          连贯性，不应输出 patch。

        Args:
            project_title: 小说标题。
            genre: 题材/类型。
            scope: 修复范围（'volume' 或 'book'）。
            quality_report: 质检报告，含 issues 与 must_fix_chapter_numbers。
            chapters: 章节列表，可含 ``_context_only=True`` 标记的上下文章节。
            story_bible_context: 故事圣经摘要（人物/设定/故事线）。
            global_outline_context: 全书卷线蓝图。
            word_budget_context: 篇幅与字数约束说明。
            realm_whitelist: 合法境界名白名单，为 None 时不注入境界约束。
            character_life_state_ledger: 角色生死台账，为空时不注入生死约束。
            positioning_context: 立项定位上下文（爽点/禁忌/节奏）。

        Returns:
            含 ``summary`` 和 ``patches`` 列表的 dict；
            AI 调用或 JSON 解析失败时返回 ``{"error": ..., "patches": []}``.
        """
        # ── 分离问题章节与上下文章节，分别格式化 ──────────────────────────────
        problem_lines: list[str] = []
        context_lines: list[str] = []

        def _fmt_chapter(ch: dict, label_prefix: str = "") -> str:
            return " | ".join([
                f"{label_prefix}第{ch.get('number', '?')}章：{ch.get('title', '未命名')}",
                f"开篇钩子：{ch.get('opening_hook', '')}",
                f"核心事件：{ch.get('core_event', '')}",
                f"人物变化：{ch.get('character_change', '')}",
                f"伏笔：{ch.get('foreshadow', '')}",
                f"章末钩子：{ch.get('end_hook', '')}",
            ])

        for ch in chapters:
            if ch.get("_context_only"):
                context_lines.append(_fmt_chapter(ch, label_prefix="[上下文] "))
            else:
                problem_lines.append(_fmt_chapter(ch))

        # ── 各约束块 ───────────────────────────────────────────────────────────
        life_block = ""
        if character_life_state_ledger.strip():
            life_block = (
                f"\n{self._clip_context(character_life_state_ledger, 1200, None, field_name='life_ledger')}\n"
                "【生死修复硬约束 — 必须严格遵守，否则质检分数将永远停在55分】\n"
                "死亡检测会扫描每章的全部5个字段：title / opening_hook / core_event / character_change / end_hook。\n"
                "只要任意一个字段里「角色名」附近22字符内出现死亡词（斩杀/殒落/身死/战死等），就判为死亡。\n"
                "因此：\n"
                "① 若需移除某章的「死亡判定」（如假死/血遁），必须同时清除该章ALL 5个字段中所有包含「角色名+死亡词」的句子；\n"
                "② 再现章必须让「角色名」紧邻（≤8字符内）出现复活触发词之一：残魂/化身/分身/传承/假死/意志/魂魄/寄宿/虚影/执念；\n"
                "   示例合法写法：「铁手残魂借助遗物出现」「赵执事以化身归来」「XX以传承形式影响主角」；\n"
                "   不合法：「虽然铁手已死，但此处有残魂云云」（间距超过22字符，检测不通过）；\n"
                "③ 每处角色生死问题必须提供死亡章+再现章两处patch，缺一不可。\n"
            )

        realm_block = ""
        if realm_whitelist:
            whitelist_str = "、".join(sorted(realm_whitelist))
            realm_block = (
                f"\n【境界体系强约束】\n"
                f"本项目合法境界白名单：{whitelist_str}\n"
                f"禁止使用传统修真 IP 境界词（筑基/金丹/元婴/化神/炼气等），须从白名单取词。\n"
                f"注意：「炼化神火」「化神炉」等复合词中的「化神」不是境界名，勿误删或误改。\n"
            )

        positioning_block = (
            f"\n{self._clip_context(positioning_context, 1200, None, field_name='positioning')}\n"
            "修复要求：补丁必须符合以上立项定位（爽点/节奏/禁忌），"
            "不得因修复结构问题而牺牲定位约束（如把打脸场景改成内省独白）。\n"
            if positioning_context else ""
        )

        linter_block = ""
        if linter_context.strip():
            linter_block = (
                f"\n{self._clip_context(linter_context, 2000, None, field_name='linter_context')}\n"
            )

        # 根据质检问题类型生成差异化修复指引
        issue_hints_block = self._build_issue_type_hints(quality_report)

        # 上下文章节段落（仅在存在时插入）
        context_block = ""
        if context_lines:
            context_block = (
                "\n【邻近章节上下文（仅供参考连贯性，禁止对这些章节输出 patch）】\n"
                + self._clip_context(
                    "\n".join(context_lines), 3000, None, field_name="context_chapters"
                )
                + "\n"
            )

        system = "你是资深网文大纲修复主编。你只输出可应用的大纲字段补丁，严格返回JSON。"
        prompt = f"""小说：《{project_title}》（{genre}）
修复范围：{scope}

【故事圣经账本】
{self._clip_context(story_bible_context, 3200, None, field_name="story_bible") or '（未提供）'}

【全书卷线蓝图】
{self._clip_context(global_outline_context, 5000, None, field_name="global_outline") or '（未提供）'}

【篇幅与字数约束】
{self._clip_context(word_budget_context, 600, None, field_name="word_budget") or '（未提供）'}
{positioning_block}{linter_block}{realm_block}{life_block}{issue_hints_block}
【质检问题】
{self._clip_context(json.dumps(quality_report, ensure_ascii=False), 6000, None, field_name="quality_report")}

【待修复章节计划】
{self._clip_context(chr(10).join(problem_lines), 8000, None, field_name="chapter_lines_repair")}
{context_block}
请生成大纲修复补丁，要求：
1. 只对「待修复章节」输出 patch，禁止对标注「[上下文]」的邻近章节输出 patch。
2. 参考邻近章节上下文，确保修复后的开篇钩子/章末钩子与前后章节自然衔接。
3. 如果问题跨多章，按章节分别给出 patch；每个 patch 必须能独立应用。
4. 修复要保持世界观、人物状态、道具象征、伏笔承接和下一卷钩子一致。
5. 每个字段必须是可直接替换的短文本，不写解释性长文。
6. 修复后要保持篇幅兑现能力：不能把中后期关键阶段压缩成速刷；必要时通过补强过渡与代价链来恢复长篇承载力。
7. 若质检报「修真术语」但原文是「炼化神火」等动作/宝物复合词，不要改动该词；仅替换真正的境界名误用。

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
            task="outline.repair",
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
