"""Bootstrap Step 12：开局追读承诺 + ReaderPromise 种子。"""

from __future__ import annotations

from typing import Any

from app.models import Project
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.reader_promise_seed import seed_reader_promises


async def gen_opening_contract(svc: Any, project: Project, ctx: dict) -> dict:
    system = (
        "你是有30年经验的网络小说总编辑，专门做开局追读策划。"
        "只返回 JSON，不要任何解释文字。"
    )

    positioning = ctx.get("positioning") or {}
    tropes = positioning.get("tropes", [])
    pace_type = positioning.get("pace_type", "medium")
    target_audience = positioning.get("target_audience", "")

    prompt = f"""小说：《{ctx.get('project_title', '未命名')}》（{ctx.get('genre', '')}）
主角：{ctx.get('protagonist', '主角')}  起点境界：{ctx.get('power_level_names', ['（未知）'])[0] if ctx.get('power_level_names') else '（未知）'}
创意：{ctx.get('logline', '')}
核心爽点：{', '.join(tropes) or '（未设定）'}
节奏类型：{pace_type}
目标读者：{target_audience or '（未设定）'}
世界观：{ctx.get('world_overview', '')[:200]}
卷一概述：{(ctx.get('volumes_summary') or '').split('|')[0][:100]}

请为本书开局前10章制定「追读承诺清单」，这是编辑决定是否签约的核心审核项。
返回JSON：
{{
  "first_200_words_test": "第一章前200字必须完成的3件事：1) xxx 2) xxx 3) xxx（具体到场景/信息/情绪，不要废话）",
  "chapter1_hook": "第1章末尾钩子：读者读完第1章后必须知道答案才肯继续的那个问题（一句话）",
  "chapter3_payoff": "第3章小爽点：主角在前3章内必须获得的第一次具体反转/胜利/资源（要具体，不要'小小展示实力'这种废话）",
  "chapter5_foreshadow": "第5章必须埋下的长线伏笔：能支撑读者追到第30章的那个谜（一句话，具体到人物或秘密）",
  "chapter10_subscribe_reason": "第10章末尾：读者为什么要付费订阅第11章？给出一个让人无法放下的悬念设计（具体手法：强敌登场/秘密揭示/关系逆转/etc）",
  "opening_traps_to_avoid": ["开局必须避免的3个常见坑（针对本书题材和爽点类型的具体风险）"],
  "chapter_rhythm": "前10章节奏设计：哪章快哪章慢，何时第一次打脸，何时第一次建立情感连接（50字内）"
}}
要求：每个字段必须结合本书具体设定给出，禁止使用通用模板语言。"""

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=2048, task="bootstrap.opening_contract"
        )
        contract = parse_json(raw)
        if not isinstance(contract, dict):
            contract = {}
    except Exception:
        contract = {}

    try:
        extra = project.extra or {}
        extra["opening_contract"] = contract
        project.extra = extra
        svc.db.commit()
    except Exception:
        pass

    ctx["opening_contract"] = contract

    if contract:
        milestone_map = [
            {
                "key": "chapter1_hook",
                "promise_type": "chapter_ending",
                "source_chapter_number": 1,
                "expected_chapter_window": 2,
                "priority": 5,
                "audience_aware": 4,
            },
            {
                "key": "chapter3_payoff",
                "promise_type": "protagonist_claim",
                "source_chapter_number": 0,
                "expected_chapter_window": 3,
                "priority": 4,
                "audience_aware": 3,
            },
            {
                "key": "chapter5_foreshadow",
                "promise_type": "chapter_ending",
                "source_chapter_number": 5,
                "expected_chapter_window": 25,
                "priority": 3,
                "audience_aware": 2,
            },
            {
                "key": "chapter10_subscribe_reason",
                "promise_type": "chapter_ending",
                "source_chapter_number": 10,
                "expected_chapter_window": 1,
                "priority": 5,
                "audience_aware": 5,
            },
            {
                "key": "first_200_words_test",
                "promise_type": "name_implication",
                "source_chapter_number": 1,
                "expected_chapter_window": 0,
                "priority": 2,
                "audience_aware": 1,
            },
        ]
        seed_entries = []
        for m in milestone_map:
            text = contract.get(m["key"])
            if not text:
                continue
            seed_entries.append({
                "text": text,
                "promise_type": m["promise_type"],
                "source_chapter_number": m["source_chapter_number"],
                "expected_chapter_window": m["expected_chapter_window"],
                "priority": m["priority"],
                "audience_aware": m["audience_aware"],
                "contract_key": m["key"],
            })
        seed_reader_promises(svc, project, seed_entries, origin="bootstrap_opening_contract")

    return contract
