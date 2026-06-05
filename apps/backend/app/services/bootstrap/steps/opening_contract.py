"""Bootstrap Step 12：开局追读承诺 + ReaderPromise 种子。"""

from __future__ import annotations

from typing import Any

from app.models import OutlineNode, Project
from app.services.bootstrap.opening_contract_io import persist_opening_contract
from app.services.bootstrap.parse import parse_json
from app.services.bootstrap.prompts.opening_contract import build_opening_contract_prompt
from app.services.bootstrap.reader_promise_seed import seed_reader_promises
from app.services.llm_token_budgets import max_tokens_bootstrap_completion
from app.services.xuanhuan_lexicon import (
    is_xuanhuan_like_genre,
    sanitize_xuanhuan_text,
)


def _load_vol1_node(svc: Any, project: Project) -> OutlineNode | None:
    return (
        svc.db.query(OutlineNode)
        .filter(
            OutlineNode.project_id == project.id,
            OutlineNode.node_type == "volume",
            OutlineNode.sort_order == 0,
        )
        .first()
    )


async def gen_opening_contract(svc: Any, project: Project, ctx: dict) -> dict:
    vol1 = _load_vol1_node(svc, project)
    system, prompt = build_opening_contract_prompt(project, ctx, vol1=vol1)
    genre = ctx.get("genre", project.genre or "玄幻")

    try:
        raw = await svc._call_with_retry(
            system, prompt, max_tokens=max_tokens_bootstrap_completion(), task="bootstrap.opening_contract"
        )
        contract = parse_json(raw)
        if not isinstance(contract, dict):
            contract = {}
    except Exception:
        contract = {}

    if contract and is_xuanhuan_like_genre(genre):
        cleaned: dict = {}
        for key, val in contract.items():
            if isinstance(val, str):
                cleaned[key] = sanitize_xuanhuan_text(val)
            elif isinstance(val, list):
                cleaned[key] = [
                    sanitize_xuanhuan_text(str(x)) if isinstance(x, str) else x
                    for x in val
                ]
            else:
                cleaned[key] = val
        contract = cleaned

    if contract:
        try:
            persist_opening_contract(svc, project, contract)
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
