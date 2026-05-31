"""outline_quality 契约、台账与回灌块单测。"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from app.services.outline_linter.schemas import LinterIssue, LinterReport
from app.services.outline_quality.contract import (
    Issue,
    IssueSet,
    issue_fingerprint,
    issue_set_from_linter_report,
)
from app.services.outline_quality.feedback_block import build_issue_feedback_block
from app.services.outline_quality.issue_log import record_issue_set, top_frequent_issues


def test_issue_fingerprint_stable():
    fp1 = issue_fingerprint("CH-04", "extra.choice_cost", 7)
    fp2 = issue_fingerprint("CH-04", "extra.choice_cost", 7)
    fp3 = issue_fingerprint("CH-04", "extra.choice_cost", 8)
    assert fp1 == fp2
    assert fp1 != fp3


def test_issue_set_from_linter_report():
    report = LinterReport(
        issues=[
            LinterIssue(
                rule_id="CH-04",
                severity="critical",
                scope="chapter",
                message="选择代价为空",
                field="extra.choice_cost",
                chapter_number_in_volume=3,
                suggestion="补写具体代价",
            ),
        ],
    )
    report.finalize_status()
    issue_set = issue_set_from_linter_report(report, volume_node_id="vol-1")
    assert issue_set.volume_node_id == "vol-1"
    assert len(issue_set.issues) == 1
    assert issue_set.issues[0].dimension == "chapter_craft"
    assert issue_set.issues[0].fingerprint == issue_fingerprint("CH-04", "extra.choice_cost", 3)


def test_build_issue_feedback_block_empty():
    assert build_issue_feedback_block([]) == ""


def test_build_issue_feedback_block_includes_rule_and_fewshot():
    block = build_issue_feedback_block([
        {
            "rule_id": "CH-04",
            "dimension": "chapter_craft",
            "count": 5,
            "severity": "critical",
            "suggestion": "补写 choice_cost",
            "field": "extra.choice_cost",
        },
    ])
    assert "CH-04" in block
    assert "累计命中 5 次" in block
    assert "选择代价" in block
    assert "反例" in block


def test_record_issue_set_inserts_new_row():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    issue_set = IssueSet(
        volume_node_id=str(uuid.uuid4()),
        issues=[
            Issue(
                rule_id="CH-04",
                severity="critical",
                dimension="chapter_craft",
                message="空代价",
                field="extra.choice_cost",
                chapter_number=1,
            ),
        ],
    )
    count = record_issue_set(db, uuid.uuid4(), issue_set, commit=False)
    assert count == 1
    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.commit.assert_not_called()


def test_record_issue_set_dedupes_same_fingerprint_before_flush():
    """同批 IssueSet 内重复指纹不得二次 INSERT（flush 前 query 看不见 pending 行）。"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    vol_id = str(uuid.uuid4())
    issue_set = IssueSet(
        volume_node_id=vol_id,
        issues=[
            Issue(
                rule_id="CH-07",
                severity="medium",
                dimension="chapter_craft",
                message="第7章偏短",
                field="word_budget",
                chapter_number=7,
            ),
            Issue(
                rule_id="CH-07",
                severity="high",
                dimension="chapter_craft",
                message="第7章偏短（重复）",
                field="word_budget",
                chapter_number=7,
            ),
        ],
    )
    count = record_issue_set(db, uuid.uuid4(), issue_set, commit=False)
    assert count == 2
    assert db.add.call_count == 1
    added = db.add.call_args[0][0]
    assert added.occurrence_count == 2
    assert added.severity == "high"
    db.flush.assert_called_once()


def test_record_issue_set_increments_existing():
    db = MagicMock()
    existing = MagicMock()
    existing.occurrence_count = 2
    existing.suggestion = "旧建议"
    db.query.return_value.filter.return_value.first.return_value = existing
    issue_set = IssueSet(
        volume_node_id=str(uuid.uuid4()),
        issues=[
            Issue(
                rule_id="CH-04",
                severity="high",
                dimension="chapter_craft",
                message="更新描述",
                field="extra.choice_cost",
                chapter_number=1,
                suggestion="新建议",
            ),
        ],
    )
    count = record_issue_set(db, uuid.uuid4(), issue_set, commit=True)
    assert count == 1
    assert existing.occurrence_count == 3
    assert existing.message == "更新描述"
    assert existing.suggestion == "新建议"
    db.commit.assert_called_once()


def test_top_frequent_issues_maps_worst_severity():
    """severity_rank 取 min 时，critical+medium 应返回 critical 而非字典序 medium。"""
    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    row = MagicMock()
    row.rule_id = "CH-04"
    row.dimension = "chapter_craft"
    row.total = 10
    row.severity_rank = 0
    row.suggestion = "补代价"
    row.field = "extra.choice_cost"
    mock_q.group_by.return_value.order_by.return_value.limit.return_value.all.return_value = [row]

    result = top_frequent_issues(db, uuid.uuid4(), min_severity="high")
    assert len(result) == 1
    assert result[0]["severity"] == "critical"
    assert result[0]["count"] == 10
