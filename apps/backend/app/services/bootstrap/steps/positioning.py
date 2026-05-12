"""Bootstrap Step 0：立项会议（题材定位）。"""

from __future__ import annotations

from typing import Any

from app.services.bootstrap.parse import parse_json


async def gen_positioning(svc: Any, ctx: dict) -> dict:
    """召开立项会议：从 logline 推出读者画像 / 爽点类型 / 打脸频率等全局约束。"""
    system = (
        "你是有30年经验的网络小说总编辑。从一句话创意推导出可执行的题材定位，"
        "只返回 JSON，不要任何解释文字。"
    )
    prompt = f"""创意：{ctx['logline']}
作者补充：{(ctx.get('premise') or '')[:600] or '（未填写，请独立推导）'}

请基于以上创意，做一次「立项会议」决策，返回 JSON：
{{
  "target_audience": "目标读者画像（性别/年龄段/平台调性，例：男频 18-30 岁起点向）",
  "tropes": ["核心爽点类型 3-5 个，从：重生/系统/苟道/扮猪吃虎/无敌流/种田流/红尘炼心/打脸装x/团宠/收徒养崽/复仇/逆袭 等中筛选最契合的"],
  "reference_works": ["3 部参照作品（同流派代表作，仅作基调参考，禁止抄袭）"],
  "selling_point": "一句话卖点钩子（30 字内，必须能贴在书籍封面）",
  "face_slap_pattern": "打脸节奏（例：每 3 章一小、每 10 章一中、每卷一大）",
  "emotional_arc": "情感线占比（none/low/medium/high，对应 0%/10%/25%/40%）",
  "pace_type": "节奏类型（fast=番茄式爽快 / medium=起点中速 / slow=猫腻式文笔）",
  "taboo_lines": ["禁忌边界 2-4 条（禁止涉及的题材/主题）"],
  "market_risk": "市场风险评估（同质化程度/受众规模/题材饱和度，各一句，合计50字内）",
  "differentiation_durability": "差异化持续性：你的核心差异化能撑几卷？第几卷之后最可能暴露同质化？建议提前布局什么钩子来对冲？（60字内）",
  "hook_test": "封面50字钩子：用50字以内写出这本书的书架推荐语，然后自评'一个从未看过此类书的28岁男/女读者，看到这50字的点击意愿（1-10分）'，格式：推荐语｜自评分:X｜理由（30字）"
}}

要求：
1. tropes 必须互相协调，禁止"种田流+无敌流"这类自相矛盾组合
2. reference_works 必须是同流派作品（不要跨流派类比）
3. 若 logline 暗示女频题材，target_audience 不要硬扭成男频
4. market_risk 必须诚实评估，不要只说好话——若同质化风险高，直接指出
5. hook_test 的自评分要实事求是，6分以下要给出"如何提升钩子吸引力"的建议
6. 严禁返回任何解释，仅返回 JSON。"""

    raw = await svc._call_with_retry(
        system,
        prompt,
        max_tokens=2560,
        task="bootstrap.positioning",
    )
    try:
        data = parse_json(raw)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    for k in (
        "target_audience", "selling_point", "face_slap_pattern",
        "emotional_arc", "pace_type",
        "market_risk", "differentiation_durability", "hook_test",
    ):
        v = data.get(k)
        if not isinstance(v, str):
            data[k] = ""
    for k in ("tropes", "reference_works", "taboo_lines"):
        v = data.get(k)
        if not isinstance(v, list):
            data[k] = []
        else:
            data[k] = [str(x).strip() for x in v if x and isinstance(x, (str, int, float))]
    return data
