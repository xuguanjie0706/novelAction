"""番茄 Bootstrap 归一化：标准列映射单测。"""
from app.services.bootstrap.fanqie_normalize import (
    apply_normalized_chapter_plan,
    build_chapter_hook,
    build_chapter_summary,
    infer_chapter_title,
    pacing_from_rhythm_tag,
)


def test_infer_title_from_core_event_when_missing():
    ch = {"core_event": "莫苍生当众撕碎退婚书并觉醒神脉"}
    assert infer_chapter_title(4, ch) != "第4章"
    assert "莫苍生" in infer_chapter_title(4, ch)


def test_build_summary_prefers_core_event():
    ch = {"core_event": "核心事件全文", "structure": {"act_1_setup": "铺垫"}}
    assert build_chapter_summary(ch) == "核心事件全文"


def test_build_hook_merges_commitment_on_ch5():
    ch = {
        "ending_hook": "悬念问句？",
        "commitment_hook": "强敌登门",
    }
    hook = build_chapter_hook(ch, 5)
    assert hook
    assert "悬念" in hook
    assert "强敌" in hook


def test_apply_normalized_sets_standard_columns():
    from app.models import OutlineNode

    ch = {
        "title": "手撕至尊骨",
        "core_event": "当众生撕神骨",
        "first_slap_scene": "柳若烟跪地",
        "ending_hook": "下一章谁来了？",
        "completion_rate_target": 45,
        "emotion_peak": "暴爽",
    }
    node = OutlineNode(
        project_id="00000000-0000-0000-0000-000000000001",
        node_type="chapter_plan",
        title="旧标题",
        sort_order=3,
    )
    apply_normalized_chapter_plan(node, 3, ch, first_slap_ch=3)
    assert node.title == "手撕至尊骨"
    assert node.summary == "当众生撕神骨"
    assert node.hook == "下一章谁来了？"
    assert node.power_milestone == "柳若烟跪地"
    assert node.expected_words == 2100
    assert node.extra.get("has_face_slap") is True
    assert node.extra.get("core_event")
    assert node.extra.get("obstacle") is None or node.conflict


def test_pacing_from_rhythm_tag():
    assert pacing_from_rhythm_tag("big_win") == "climax"
    assert pacing_from_rhythm_tag("transition") == "slow"


def test_normalize_legacy_opening_sort_orders():
    from app.models import OutlineNode
    from app.services.bootstrap.fanqie_volume_expand import normalize_legacy_opening_sort_orders

    nodes = [
        OutlineNode(
            project_id="00000000-0000-0000-0000-000000000001",
            node_type="chapter_plan",
            title="a",
            sort_order=1,
            extra={"bootstrap_fanqie": True},
        ),
        OutlineNode(
            project_id="00000000-0000-0000-0000-000000000001",
            node_type="chapter_plan",
            title="b",
            sort_order=5,
            extra={"bootstrap_fanqie": True},
        ),
    ]
    normalize_legacy_opening_sort_orders(nodes)
    assert nodes[0].sort_order == 0
    assert nodes[1].sort_order == 4
    from app.services.bootstrap.fanqie_volume_expand import chapter_index_from_node

    assert chapter_index_from_node(nodes[1]) == 5
