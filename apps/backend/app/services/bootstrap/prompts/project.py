"""Bootstrap Step 1：项目基础信息生成 prompt。

书名海选（15~20个，一次 LLM 调用内打分排序）+ 结构化 premise + 结构化 world_overview。

设计动机（CLAUDE.md「Prompt 层」）：
- 单次 prompt 字面量 ≥ 30 行必须抽到 prompts/*.py。
- 书名 single-shot 是整个 pipeline ROI 最低的省法；真实编辑部一本书列 20+ 备选再筛。
- premise 由 markdown blob 改为结构化对象，下游可精确取 .core_conflict 而非截字符串。
- world_overview 解除 500 字上限，按块存储，下游按需取块。
"""

from __future__ import annotations

import json

# ── 命名策略指南 ─────────────────────────────────────────────────────

TITLE_STRATEGY_GUIDE = """\
强制覆盖 6 种策略（每种至少 2 个，合计 15~20 个候选）：
• 意象型：借物借景，有画面感（如"斗破苍穹""完美世界""择天记"）
• 冲突型：点明核心矛盾或成就目标（如"我有一座冒险屋""全球高武"）
• 反差型：身份/能力反差制造张力（如"废柴逆天""神医凰后""最强弃少"）
• 悬念型：制造好奇或开放式引导点击（如"诡秘之主""神秘让我强大""深渊独行者"）
• 数量词型：数量词强化气势（如"万古神帝""一剑独尊""亿万星辰如你眼"）
• 人物/称号型：以身份/称号/绰号命名（如"大主宰""剑来""至尊神医"）

评分维度（0~10 分制，可用 0.5 步进）：
• click_score：3 秒点击冲动——读者扫到标题的本能冲动（陌生感 × 期待感）
• fit_score：与本作题材/爽点/主角风格的契合度
按 total_score（两项之和）从高到低排列；排名第一者即为本书正式书名。"""

# ── 结构化 premise 字段指南 ──────────────────────────────────────────

PREMISE_STRUCT_GUIDE = """\
以下字段各自独立，不写 markdown blob，不写空话，每条可直接落地作为作者创作基线：
• positioning   ：目标读者群 / 市场定位 / 题材标签（20~50字）
• core_sentence ：一句话核心，≤30字，可直接用作封面宣传语
• theme         ：主题与命题——作者最终想传递的那句话（≤50字）
• core_conflict ：两股力量的根本对立（30~60字，具体到人/势力层面）
• protagonist   ：主角概况——身份起点 + 核心特质 + 成长方向（≤100字）
• ending_tendency：结局倾向（类型关键词 + 一句理由，如"大团圆——读者需要情绪出口"）
• closure_boundary：收束边界——最坏情形，帮助作者守住底线（30~60字）
• taboos        ：本书绝对不写的内容（具体列举，≥3条）
• pov           ：叙事视角 + 特殊叙述技巧（如有，例如"第三人称限知视角，偶用上帝视角"）
• word_count_type：类型与篇幅，必须与【全书字数目标（硬性约束）】保持一致"""

# ── 结构化 world_overview 字段指南 ──────────────────────────────────

WORLD_OVERVIEW_STRUCT_GUIDE = """\
每块独立，解除字数上限，下游按需取块（summary 块放在最前以兼容下游 [:300] 截取）：
• summary      ：核心速览（150~250字），必须覆盖力量/势力/规则三要素；截取后上下文自洽
• power_system ：力量体系——等级划分/修炼路径/上限设定/特殊规则（可详述，无字数限制）
• factions     ：势力格局——主要势力名称/势力范围/相互关系/主要矛盾（详述）
• social_rules ：社会运行规则——阶级秩序/核心法律/经济结构/最高禁忌
• geography    ：地理格局——世界结构/重要地点/空间尺度感
• history      ：历史背景与谜团——关键历史事件/悬而未解之谜/与当下剧情的潜在关联"""


# ── JSON 模板（LLM 输出结构参考） ────────────────────────────────────

_JSON_SCHEMA = """\
{
  "title_candidates": [
    {
      "title": "候选书名（2~8字）",
      "strategy": "意象型",
      "reasoning": "一句话理由（≤30字）",
      "click_score": 8.5,
      "fit_score": 9.0,
      "total_score": 17.5
    }
  ],
  "genre": "玄幻",
  "premise": {
    "positioning": "",
    "core_sentence": "",
    "theme": "",
    "core_conflict": "",
    "protagonist": "",
    "ending_tendency": "",
    "closure_boundary": "",
    "taboos": "",
    "pov": "",
    "word_count_type": ""
  },
  "world_overview": {
    "summary": "",
    "power_system": "",
    "factions": "",
    "social_rules": "",
    "geography": "",
    "history": ""
  },
  "story_core": {
    "drive": "成长/复仇/守护等",
    "conflict": "核心矛盾",
    "theme": "主题",
    "differentiation": "与同类小说的差异化"
  }
}"""


def build_project_prompt(ctx: dict, length_block: str) -> str:
    """构造 Step 1 主 prompt：书名海选 + 结构化 premise + 结构化 world_overview。

    所有内容在一次 LLM 调用中完成，选名与打分在同一次输出内排序。

    Args:
        ctx: Bootstrap 上下文，至少含 logline / positioning（可空）/ premise（可空）。
        length_block: 由 book_length_constraints_for_prompt 生成的字数硬约束片段。

    Returns:
        完整 prompt 字符串，要求 LLM 只返回 JSON。
    """
    logline = ctx.get("logline", "")
    positioning = ctx.get("positioning") or {}
    prior_premise = (ctx.get("premise") or "")[:600]

    positioning_block = ""
    if isinstance(positioning, dict) and positioning:
        positioning_block = (
            "\n【立项定位（必须严格遵守）】\n"
            + json.dumps(positioning, ensure_ascii=False, indent=2)
            + "\n"
        )

    prior_block = f"\n作者补充说明：{prior_premise}\n" if prior_premise else ""

    return (
        f"创意：{logline}\n"
        f"{prior_block}"
        f"{positioning_block}"
        f"{length_block}\n\n"
        "你是资深网文策划编辑。在一次输出中完成书名海选、结构化立意档案、结构化世界观三件事。\n\n"
        "【一、书名海选（15~20个候选）】\n"
        f"{TITLE_STRATEGY_GUIDE}\n\n"
        "【二、立意与类型（结构化档案，非 markdown blob）】\n"
        f"{PREMISE_STRUCT_GUIDE}\n\n"
        "【三、世界观（结构化，每块独立存储）】\n"
        f"{WORLD_OVERVIEW_STRUCT_GUIDE}\n\n"
        f"返回如下结构的 JSON（只返回 JSON，不加任何解释文字）：\n{_JSON_SCHEMA}\n\n"
        "约束：\n"
        "1. title_candidates 必须按 total_score 降序排列，第一条即为正式书名\n"
        "2. premise 每字段可直接落地作为创作基线，禁止空话与通用废话\n"
        "3. world_overview.summary 单独截取时语义完整，必须覆盖力量/势力/规则三要素\n"
        "4. word_count_type 必须与【全书字数目标（硬性约束）】保持一致\n"
        "5. 只返回 JSON，不要其他任何内容"
    )
