"""读者心理模拟 Mixin — 模拟目标读者追读意愿评估与流失风险分析。"""
from __future__ import annotations

import json
import re
from app.services.llm_token_budgets import min_completion_tokens


class ReaderPsychologyMixin:
    async def reader_psychology_sim(
        self,
        project_title: str,
        genre: str,
        recent_chapters: list[dict],
        positioning: dict | None = None,
        current_chapter_number: int = 0,
    ) -> dict:
        """读者心理模拟：模拟目标读者阅读最近若干章后的感受。

        输出追读意愿评分和流失风险点。

        Args:
            project_title: 书名。
            genre: 类型标签。
            recent_chapters: 最近10章的摘要，每条含 title/summary/hook_strength/
                             subscribe_intent_score。
            positioning: Project.extra.positioning（目标读者画像、爽点类型等）。
            current_chapter_number: 当前已写章数。

        Returns:
            dict with keys: read_through_score, score_basis, trend, trend_note,
                           dropout_risks, strengths, editor_verdict, immediate_action
        """
        if not recent_chapters:
            return {"error": "no chapters provided"}

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
            max_tokens=min_completion_tokens(),
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
