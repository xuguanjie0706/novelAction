"""专项大纲质检 Mixin。

设计动机
--------
原 outline_quality_check 一次性检查9个维度，导致每个维度的检查深度不足。
本模块将质检拆为三个专注单一维度的方法，各自使用低温度确保 JSON 稳定：

- outline_check_causality   : 因果链（上一章选择→本章事件）
- outline_check_character_arc: 人物弧（欲望/选择/代价的连贯性）
- outline_check_foreshadow_audit: 伏笔审计（埋/收配对 + 主题共鸣）

调用建议：三个方法可并行调用，各返回独立问题列表，由调用方合并后展示给用户。
"""

from __future__ import annotations

import json
import re
from app.services.llm_token_budgets import min_completion_tokens


class OutlineChecksMixin:
    async def outline_check_causality(
        self,
        project_title: str,
        chapters: list[dict],
        prior_end_hook: str = "",
    ) -> dict:
        """专项质检：章节间因果链。

        只检查一件事：上一章的「选择代价」是否真正驱动了本章「核心事件」。
        使用低温度确保 JSON 输出稳定。

        Args:
            project_title: 项目名称。
            chapters: 章节计划列表，每项含 number/title/protagonist_choice/
                      choice_cost/core_event/end_hook 字段。
            prior_end_hook: 上一批最后一章的章末钩子（用于检查批次衔接）。

        Returns:
            {"issues": [...], "broken_pairs": [...], "summary": str}
        """
        lines = []
        for ch in chapters:
            lines.append(
                f"第{ch.get('number', '?')}章《{ch.get('title', '')}》 | "
                f"选择：{ch.get('protagonist_choice', ch.get('core_event', ''))} | "
                f"代价：{ch.get('choice_cost', '')} | "
                f"核心事件：{ch.get('core_event', '')} | "
                f"章末钩子：{ch.get('end_hook', '')}"
            )

        prior_hook_block = (
            f"【上一批最后一章章末钩子（本批第一章必须回应）】\n{prior_end_hook}\n"
            if prior_end_hook else ""
        )

        system = "你是网文结构审稿专家，只检查章节因果链，严格返回JSON。"
        prompt = f"""小说：《{project_title}》
{prior_hook_block}
【待检章节（按顺序）】
{chr(10).join(lines)}

只检查一件事：相邻两章之间是否存在真实的因果链接。
具体标准：
- 第N章的「选择代价（choice_cost）」是否在逻辑上必然导致第N+1章的「核心事件（core_event）」
- 如果第N+1章的核心事件与第N章的代价无关，则视为因果断裂
- 章末钩子承诺的悬念，必须在下一章章首被回应（不要求立刻解决，但要被承接）
- 若提供了「上一批末章末钩子」，检查本批第一章是否回应了它

返回JSON（不要任何额外文字）：
{{
  "summary": "因果链整体评价，一句话",
  "broken_pairs": [
    {{
      "from_chapter": 3,
      "to_chapter": 4,
      "from_cost": "第3章的选择代价原文",
      "to_event": "第4章的核心事件原文",
      "reason": "为什么这两章之间因果链断裂"
    }}
  ],
  "hook_misses": [
    {{
      "chapter": 5,
      "promised": "第5章章末钩子承诺了什么",
      "delivered": "第6章实际开篇回应了什么（或未回应）"
    }}
  ],
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "chapter_numbers": [3, 4],
      "description": "具体问题说明",
      "fix_hint": "修复方向（修改哪章的哪个字段，方向是什么）"
    }}
  ]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=min_completion_tokens(),
            context={"operation": "outline_check_causality"},
            task="quality.causality_check",
        )
        return self._parse_check_response(response)

    async def outline_check_character_arc(
        self,
        project_title: str,
        protagonist_name: str,
        chapters: list[dict],
        character_summary: str = "",
        protagonist_psychology: str = "",
    ) -> dict:
        """专项质检：主角人物弧度。

        只检查主角的欲望/选择/代价在全批次中是否形成连贯、有成长的弧线。
        重点识别"木偶主角"（被事件推着走，没有主动欲望和选择）。

        Args:
            project_title: 项目名称。
            protagonist_name: 主角名称。
            chapters: 章节计划列表，含 protagonist_want/protagonist_obstacle/
                      protagonist_choice/choice_cost/character_change 字段。
            character_summary: 主角基本设定（性格/背景/初始状态）。
            protagonist_psychology: 主角心理档案（core_wound/biggest_lie 等）。

        Returns:
            {"arc_score": int, "issues": [...], "passive_chapters": [...], "summary": str}
        """
        lines = []
        for ch in chapters:
            lines.append(
                f"第{ch.get('number', '?')}章《{ch.get('title', '')}》 | "
                f"想要：{ch.get('protagonist_want', '（未填）')} | "
                f"障碍：{ch.get('protagonist_obstacle', '（未填）')} | "
                f"选择：{ch.get('protagonist_choice', '（未填）')} | "
                f"代价：{ch.get('choice_cost', '（未填）')} | "
                f"人物变化：{ch.get('character_change', '')}"
            )

        psychology_block = (
            f"【主角心理档案】\n{protagonist_psychology}\n"
            if protagonist_psychology else ""
        )
        char_block = (
            f"【主角基本设定】\n{character_summary[:600]}\n"
            if character_summary else ""
        )

        system = "你是网文人物弧审稿专家，只检查主角弧线连贯性，严格返回JSON。"
        prompt = f"""小说：《{project_title}》  主角：{protagonist_name}
{char_block}{psychology_block}
【待检章节（主角维度）】
{chr(10).join(lines)}

只检查主角人物弧，具体标准：
1. 「木偶章」识别：protagonist_want 是被动回应（"不得不"/"被迫"/"为了活命"），而非主动欲望
2. 「零代价选择」：choice_cost 为空或意义不大，选择没有真实的叙事后果
3. 「性格不一致」：某章的选择方式与该主角的核心性格（参考心理档案/初始设定）明显矛盾，且没有成长原因
4. 「弧线停滞」：连续3章以上人物变化（character_change）描述相似，主角没有实质性的认知或处境变化
5. 「最大谎言」进展：如有 protagonist_psychology 中的 biggest_lie，检查该批次是否有任何章节在挑战或推进它

返回JSON（不要任何额外文字）：
{{
  "arc_score": 0,
  "summary": "主角弧线整体评价，一句话",
  "passive_chapters": [3, 7],
  "zero_cost_chapters": [5],
  "stagnation_ranges": [
    {{"from_chapter": 8, "to_chapter": 11, "reason": "为什么说停滞"}}
  ],
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "chapter_numbers": [3],
      "type": "passive/zero_cost/inconsistent/stagnation/lie_neglected",
      "description": "具体问题说明",
      "fix_hint": "如何改 protagonist_want 或 protagonist_choice 来修复"
    }}
  ]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=min_completion_tokens(),
            context={"operation": "outline_check_character_arc"},
            task="quality.character_arc_check",
        )
        return self._parse_check_response(response)

    async def outline_check_foreshadow_audit(
        self,
        project_title: str,
        theme_statement: str,
        chapters: list[dict],
        prior_ledger: str = "",
    ) -> dict:
        """专项质检：伏笔审计（配对完整性 + 主题共鸣）。

        检查两件事：
        1. 每条 埋[xxx] 是否有对应的 收[xxx]（或有合理的跨卷延续计划）
        2. 伏笔回收时是否利用了「初次读者的误解」制造惊喜（主题共鸣 vs 纯技术配对）

        Args:
            project_title: 项目名称。
            theme_statement: 全书立意（用于判断伏笔是否有主题共鸣）。
            chapters: 章节计划列表，含 foreshadow（ops 渲染摘要）/number/title 字段。
            prior_ledger: 前批未回收伏笔台账（文本格式）。

        Returns:
            {"orphan_foreshadows": [...], "theme_weak": [...], "issues": [...], "summary": str}
        """
        lines = []
        for ch in chapters:
            fs = (ch.get("foreshadow") or "").strip()
            if fs:
                lines.append(f"第{ch.get('number', '?')}章：{fs}")

        prior_block = (
            f"【前批未回收伏笔台账（本批应优先处理）】\n{prior_ledger[:3000]}\n"
            if prior_ledger else ""
        )

        system = "你是网文伏笔审稿专家，只做伏笔配对与主题共鸣审计，严格返回JSON。"
        prompt = f"""小说：《{project_title}》
全书立意：{theme_statement or '（未填写）'}
{prior_block}
【本批各章伏笔记录（由 foreshadow_ops 渲染为 埋/加热/收 摘要）】
{chr(10).join(lines) or '（本批无显式伏笔记录）'}

检查两件事：

1. 配对完整性：
   - 每条 lay（埋入）在本批或前台账中是否能找到对应 resolve（收束）
   - 孤立的 lay（无 resolve 且无跨卷延续说明）视为「孤悬伏笔」
   - 孤立的 resolve（找不到来源）视为「无源回收」

2. 主题共鸣质量：
   - 伏笔回收时，是否利用了「读者第一次看时的误解/盲区」制造「原来如此」的惊喜
   - 若某条伏笔只是信息传递（A埋B，B出现）而没有反转/深化意义，标记为「低共鸣」
   - lay 的 theme 是否与全书立意相关；无关联的伏笔质量视为低

返回JSON（不要任何额外文字）：
{{
  "summary": "伏笔整体评价，一句话",
  "orphan_foreshadows": [
    {{"chapter": 3, "content": "埋[xxx]的内容", "issue": "孤悬/无源"}}
  ],
  "theme_weak": [
    {{"chapters": [3, 12], "content": "伏笔内容", "reason": "为什么主题共鸣弱"}}
  ],
  "issues": [
    {{
      "severity": "low/medium/high/critical",
      "chapter_numbers": [3],
      "type": "orphan_foreshadow/missing_source/weak_theme/no_misdirection",
      "description": "具体问题说明",
      "fix_hint": "修复方向"
    }}
  ]
}}"""

        response = await self._call_ai(
            system,
            prompt,
            max_tokens=min_completion_tokens(),
            context={"operation": "outline_check_foreshadow_audit"},
            task="quality.foreshadow_audit",
        )
        return self._parse_check_response(response)

    def _parse_check_response(self, response: str) -> dict:
        """解析专项质检 AI 响应为 dict。

        统一处理 think 标签、markdown fence、JSON 前缀等常见格式问题。

        Args:
            response: AI 原始文本响应。

        Returns:
            解析后的 dict；失败时返回 {"error": ..., "issues": []}。
        """
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
            if "issues" not in data:
                data["issues"] = []
            return data
        except Exception as e:
            return {"error": str(e), "issues": [], "raw": response[:300]}
