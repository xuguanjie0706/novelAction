"""
Bootstrap Step 0 立项会议 — 提示词常量（> 30行字面量按红线抽出）。

单次调用版本：把「生成3候选 + 读者打分 + 自动择优」合并为一条 prompt，
让模型在同一个推理过程中完成三步任务，减少网络往返与 token 开销。

导出：
  UNIFIED_SYSTEM          — 系统角色（总编辑 + 读者模拟器 + 择优委员）
  build_unified_prompt(ctx) — 注入运行时变量后的完整 user prompt
"""

from __future__ import annotations


UNIFIED_SYSTEM = (
    "你同时扮演三个角色完成一次立项会议任务，且必须在同一个 JSON 中输出全部结果：\n"
    "① 总编辑（30年网文经验）：为创意设计 3 个真正不同的市场定位方案；\n"
    "② 读者模拟器（从未读过此类小说的28岁普通用户）：只凭封面钩子文字做直觉点击判断，"
    "绝不用行业视角，只有「会不会点进去看」的本能；\n"
    "③ 择优委员（平台算法策略顾问）：横向对比三方案后给出有据可查的最终推荐。\n"
    "三个角色必须在同一次回答中按顺序完成，只返回 JSON，不要任何解释文字。"
)


def build_unified_prompt(ctx: dict) -> str:
    """单次调用：生成3候选 + 读者评分 + 自动择优，合并为一条 user prompt。

    输出 JSON 结构：
      candidates[]: 每个候选含所有定位字段 + reader_score / reader_reason / click_trigger
      auto_selection{}: selected_index / comparison / recommended_reason / confidence

    Args:
        ctx: Bootstrap 上下文，至少含 logline / premise / target_words。

    Returns:
        注入了运行时变量的完整 user prompt 字符串。
    """
    logline = ctx.get("logline", "")
    premise = (ctx.get("premise") or "")[:600] or "（未填写，AI 独立推导）"
    target_words = int(ctx.get("target_words") or 1_200_000)
    vol_est = max(1, round(target_words / 300_000))

    return f"""创意：{logline}
作者补充：{premise}
计划字数：约 {target_words // 10000} 万字（约 {vol_est} 卷）

═══ 任务一（总编辑视角）：生成 3 个真正互竞的定位方案 ═══
方案类型必须覆盖：conservative（稳健套路）/ differentiated（差异化博出位）/ niche（小众精品），
三方案 positioning_type 不得重复，策略差异必须显著。

每个方案需包含全部以下字段：
• name            — 方案名称（4-8字）
• positioning_type — conservative | differentiated | niche
• expected_sign_rate — 高/中高/中/低（签约概率 >60%/>40%/>20%/<20%）
• ceiling         — 预期天花板（如"头部月票"/"腰部稳定"/"出圈黑马"）
• risk_level      — 低/中/高
• target_audience — 目标读者画像（性别/年龄段/平台调性）
• tropes          — 核心爽点 3-5 个（互相协调，严禁"种田流+无敌流"类自相矛盾）
• reference_works — 3部同流派真实存在的参照作品（禁止跨流派类比、禁止捏造书名）
• selling_point   — 一句话卖点（20-30字，可贴封面）
• hook_text       — 封面推荐语（50字以内，给不了解这类书的读者看的书架推荐，不含评分）
• face_slap_pattern — 打脸节奏描述
• emotional_arc   — none | low | medium | high
• pace_type       — fast | medium | slow
• taboo_lines     — 禁忌边界 2-4 条（玄幻/仙侠须含：禁止现代科技术语与商业话术，如逆向工程、解析改良、畅销榜、算法等）
• market_risk     — 市场风险诚实评估（同质化/受众/饱和度各一句，合计50字）
• differentiation_durability — 差异化持续性（60字内，指出几卷后最可能同质化）

═══ 任务二（读者模拟器视角）：对每个方案的 hook_text 打分 ═══
你现在是那个「从没看过此类书的28岁读者」——只凭封面推荐语决定点不点进去，
没有行业知识，只有直觉。在 candidates 的每个方案对象内补充：
• reader_score    — 1-10整数（10=立刻点、1=完全没兴趣）
• reader_reason   — 20字以内直觉感受（读者口吻，禁用"差异化"等行业术语）
• click_trigger   — 最触发点击的词/句（无则填 null）

═══ 任务三（择优委员视角）：横向对比后推荐最优方案 ═══
综合总编辑分析与读者评分，给出有据可查的择优建议：

返回完整 JSON（candidates 数组 + auto_selection 对象）：
{{
  "candidates": [
    {{
      "name": "...", "positioning_type": "...", "expected_sign_rate": "...",
      "ceiling": "...", "risk_level": "...", "target_audience": "...",
      "tropes": [...], "reference_works": [...], "selling_point": "...",
      "hook_text": "...", "face_slap_pattern": "...",
      "emotional_arc": "none|low|medium|high", "pace_type": "fast|medium|slow",
      "taboo_lines": [...], "market_risk": "...", "differentiation_durability": "...",
      "reader_score": 整数1-10, "reader_reason": "...", "click_trigger": "...或null"
    }},
    {{...第2方案，positioning_type必须与方案1不同...}},
    {{...第3方案，positioning_type必须与方案1、2均不同...}}
  ],
  "auto_selection": {{
    "comparison": "三方案横向对比（120字内，必须指出各自最大优势和致命弱点）",
    "recommended_reason": "选择理由（60字内，必须说明为何不选另外两个）",
    "selected_index": 0或1或2,
    "confidence": "high|medium|low"
  }}
}}
严禁返回任何解释文字，仅返回 JSON。"""
