"""draft_helpers 写前硬门与 writing_config 合并的纯逻辑单测（无 DB / 无 LLM）。"""

from types import SimpleNamespace

from app.routers.ai.draft_helpers import (
    consistency_issue_fingerprint,
    hook_chapter_mandate_active,
    list_chapter_relevant_consistency_issue_dicts,
    merge_writing_config,
    prewrite_gate_violation,
)


def test_consistency_issue_fingerprint_stable():
    row = {
        "severity": "high",
        "type": "realm_mismatch",
        "description": "主角境界与体系不符",
        "suggestion": "改人物卡",
    }
    fp1 = consistency_issue_fingerprint(row)
    fp2 = consistency_issue_fingerprint(row)
    assert fp1 == fp2
    assert len(fp1) == 64


def test_list_chapter_relevant_consistency_filters_by_manifest():
    # 条目 >5 时仅保留描述中含 manifest 人名的条目
    issues = [
        {"severity": "high", "description": f"条目{i}与配角甲矛盾", "type": "other"}
        for i in range(6)
    ]
    issues[2] = {"severity": "high", "description": "萧炎与纳兰嫣然婚约矛盾", "type": "other"}
    extra = {"consistency_issues": issues}
    rel = list_chapter_relevant_consistency_issue_dicts(extra, ["萧炎"])
    assert len(rel) == 1
    assert "萧炎" in (rel[0].get("description") or "")


def test_merge_writing_config_picks_project_extra():
    p = SimpleNamespace(
        extra={
            "writing_config": {
                "block_on_consistency_issues": True,
                "min_face_slap_payoff_score": 7.0,
            }
        }
    )
    cfg = merge_writing_config(p, None)
    assert cfg["block_on_consistency_issues"] is True
    assert cfg["min_face_slap_payoff_score"] == 7.0
    assert cfg["block_on_realm_mismatch"] is False


def test_hook_chapter_mandate_active_climax():
    ch = SimpleNamespace(sort_order=3)
    ctx = {"phase": "climax", "positioning": {"face_slap_pattern": ""}}
    assert hook_chapter_mandate_active(ctx, ch) is True


def test_prewrite_gate_consistency_requires_ack():
    """block_on + high severity + 未 ack → 返回 violation dict。"""
    p = SimpleNamespace(id="00000000-0000-0000-0000-000000000001", extra={})
    ch = SimpleNamespace(sort_order=1)
    ctx = {"chapter_manifest": ["萧炎"]}
    cfg = {
        "block_on_consistency_issues": True,
        "consistency_block_severities": ["high"],
        "block_on_realm_mismatch": False,
    }
    project_extra = {
        "consistency_issues": [
            {
                "severity": "high",
                "type": "realm_mismatch",
                "description": "萧炎当前境界不在 levels 列表",
                "suggestion": "修正",
            }
        ]
    }
    p.extra = project_extra
    viol = prewrite_gate_violation(
        db=None,  # type: ignore[arg-type]
        project=p,
        chapter=ch,
        ctx=ctx,
        cfg=cfg,
        ack_fingerprints=None,
    )
    assert viol is not None
    assert viol.get("reason") == "consistency_issues"
    assert viol.get("issues") and viol["issues"][0].get("fingerprint")

    fp = viol["issues"][0]["fingerprint"]
    cleared = prewrite_gate_violation(
        db=None,  # type: ignore[arg-type]
        project=p,
        chapter=ch,
        ctx=ctx,
        cfg=cfg,
        ack_fingerprints=[fp],
    )
    assert cleared is None
