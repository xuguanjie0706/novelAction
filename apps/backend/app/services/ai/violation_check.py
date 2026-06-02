"""
violation_check.py — AI 投稿违禁词预审 Mixin。

职责边界：
- 调用 AI 扫描章节内容，识别可能触发主流网文平台审核系统的段落。
- 不硬编码违禁词列表（词库随平台更新，AI 判断更灵活、覆盖更广）。
- 返回结构化结果：风险等级 + 问题条目列表 + 具体修改建议。
- 调用方（路由层）负责按章节分批传入，本 mixin 只处理单次调用。
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from app.services.llm_token_budgets import min_completion_tokens

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是中国网络小说平台内容合规顾问，帮助作者在投稿前发现可能触发审核系统的内容。"
    "你的任务是客观识别潜在合规风险并给出具体修改建议，不评判内容的文学价值。"
)

_PROMPT = """\
请扫描以下章节内容，识别可能被主流中文网文平台（{platform_name}）审核系统标记的段落。

常见风险类别：政治敏感内容、极端暴力/血腥描写、色情/低俗内容、赌博/诈骗相关、
毒品制造/使用、宗教敏感内容、其他明显违规表述。

【章节内容】
{content}

请返回严格 JSON，格式如下：
{{
  "overall_risk": "low|medium|high",
  "summary": "一句话总结扫描结果（如无风险可写'未检测到明显违规内容'）",
  "issues": [
    {{
      "category": "问题类别",
      "level": "warn|block",
      "excerpt": "原文片段（30字以内）",
      "reason": "可能触发审核的原因",
      "suggestion": "具体修改建议（保持故事逻辑不变的前提下如何表达）"
    }}
  ]
}}

issues 为空数组表示无风险。只返回 JSON，不要任何其他文字。\
"""


class ViolationCheckMixin:
    async def scan_violations(
        self,
        content: str,
        platform: str = "general",
        platform_name: str = "通用平台",
    ) -> dict:
        """
        AI 扫描单章内容中可能违反平台规则的段落。

        建议调用方将超长章节截断至 4000 字以内再传入，
        避免超出小上下文模型的 token 预算。

        Args:
            content: 章节纯文本内容（已去除 HTML 标签）。
            platform: 平台标识（qidian / jjwxc / fanqie / general），用于日志。
            platform_name: 平台中文名，注入 prompt 提供针对性上下文。

        Returns:
            dict 含三个字段：
              - overall_risk: "low" | "medium" | "high" | "unknown"（AI 失败时）
              - summary: 一句话总结
              - issues: list[dict]，每项含 category / level / excerpt / reason / suggestion
        """
        from app.services.bootstrap.parse import parse_json  # 避免顶层循环导入

        prompt = _PROMPT.format(
            platform_name=platform_name,
            content=(content or "")[:4000],
        )

        try:
            raw = await self._call_ai(
                _SYSTEM,
                prompt,
                max_tokens=min_completion_tokens(),
                task="quality.check",   # 低温度档，要求 JSON 稳定
                context={"operation": "violation_scan", "platform": platform},
            )
            result = parse_json(raw)
            if not isinstance(result, dict):
                raise ValueError(f"AI 返回非 dict: {type(result)}")

            # 字段兜底：确保调用方不因缺字段而报错
            result.setdefault("overall_risk", "unknown")
            result.setdefault("summary", "扫描完成")
            result.setdefault("issues", [])
            return result

        except Exception as exc:
            logger.warning("violation_scan failed (platform=%s): %s", platform, exc)
            return {
                "overall_risk": "unknown",
                "summary": f"扫描服务暂时不可用，请手动检查（错误：{exc}）",
                "issues": [],
            }
