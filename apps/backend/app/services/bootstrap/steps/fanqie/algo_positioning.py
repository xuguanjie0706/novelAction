"""Bootstrap Fanqie Step 0：算法立项。

番茄专属定位，与通用 positioning.py 的核心差异：
- 先选类型公式（从番茄热榜原型中选），不从 logline 自由推导
- 爽感宣言只能有 ONE 条，不能是混合型
- 必须输出算法友好的平台标签和完读率预估钩子
- 竞品差异化必须是具体的「第一章前 3 页」级别的可感知差异，不接受宏观描述
"""
from __future__ import annotations

from typing import Any

from app.services.bootstrap.parse import parse_json

# 番茄主流类型公式（供 AI 选择，避免生成不上架的边缘题材）
_FANQIE_ARCHETYPES = (
    "赘婿打脸流 / 系统升级流 / 重生复仇流 / 都市豪门流 / "
    "穿越种田流 / 古武觉醒流 / 学霸逆袭流 / 神豪撒币流 / "
    "末世求生流 / 星际无敌流 / 修仙打脸流 / 团宠萌宝流"
)


async def gen_algo_positioning(svc: Any, ctx: dict) -> dict:
    """
    召开番茄算法立项会议：从 logline 锁定类型公式 + ONE 核心爽感 + 竞品差异。

    产物写入 ctx['fanqie_positioning']，同时以 ctx['positioning'] 兼容项目创建步骤。

    @returns fanqie_positioning dict；校验失败三次后返回空 dict（不中断图）
    """
    system = (
        "你是有20年番茄小说运营经验的平台总编。"
        "你深知番茄算法逻辑：完读率>收藏率>评论率。"
        "只返回 JSON，不要任何解释文字。"
    )
    prompt = f"""番茄小说一句话创意：{ctx['logline']}
作者补充说明：{(ctx.get('premise') or '')[:400] or '（无）'}

可选类型公式（必须从下列中选一个最契合的，禁止自创）：
{_FANQIE_ARCHETYPES}

请做「番茄算法立项会议」，返回 JSON：
{{
  "genre_archetype": "从上列选一个，照抄原文",
  "core_satisfaction": "读者每次更新后得到的 ONE 核心爽感（15字内，必须具体：不能写'爽'，要写'看废物当众打脸贵族'这种画面感的描述）",
  "competitor_works": ["番茄/起点上同类型当前 TOP3 作品名（必须真实存在）"],
  "differentiation": "与竞品相比，本书第一章前3页（约1500字内）读者能感知到的具体差异是什么（30字内，必须是'第一章就能看到的'差异，不接受'更有深度'这类虚词）",
  "platform_tags": ["番茄算法标签 3-5 个，如：赘婿、打脸、都市、系统、重生"],
  "algo_hook": "给番茄书架推荐位设计的50字内吸引语，必须含：身份落差+爽感预告+悬念",
  "completion_rate_prediction": "预估第1章完读率（高/中/低）及理由（20字内）",
  "taboo_check": "本创意是否触碰番茄违禁题材（是/否），若是请指出"
}}

判断标准：
1. core_satisfaction 必须是读者能在脑海里「播放一段画面」的描述
2. differentiation 必须是「开局第一章内就能感知到的」，不接受「后期更精彩」
3. platform_tags 必须是番茄站内真实存在的推荐标签词
4. 若 logline 暗示的题材不适合番茄（如纯文学、政治敏感），请在 taboo_check 中说明
5. 只返回 JSON，不要解释"""

    last_err = ""
    for attempt in range(3):
        fix = (
            f"\n【上次输出未通过校验，请修正：{last_err}】"
            if last_err else ""
        )
        raw = await svc._call_with_retry(
            system, prompt + fix,
            max_tokens=1024,
            task="bootstrap.positioning",
        )
        try:
            data = parse_json(raw)
        except Exception:
            last_err = "JSON 解析失败"
            continue
        if not isinstance(data, dict):
            last_err = "根类型须为 JSON 对象"
            continue
        required = {"genre_archetype", "core_satisfaction", "competitor_works",
                    "differentiation", "platform_tags", "algo_hook"}
        missing = required - data.keys()
        if missing:
            last_err = f"缺少字段：{missing}"
            continue
        if not data.get("genre_archetype") or not data.get("core_satisfaction"):
            last_err = "genre_archetype / core_satisfaction 不能为空"
            continue
        return data
    return {}
