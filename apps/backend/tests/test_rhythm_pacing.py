"""rhythm_map → pacing_skeleton 压缩与修复单测。"""
from app.services.bootstrap.steps.fanqie.rhythm_map import _build_story_buffer_by_rule
from app.services.bootstrap.rhythm_pacing import (
    apply_rhythm_to_pacing_skeleton,
    build_pacing_skeleton_from_tags,
    is_mechanical_tag_skeleton,
    is_semantic_narrative_skeleton,
    is_tag_style_skeleton,
    refresh_opening_volume_pacing_skeleton,
    repair_rhythm_tags,
)


def _user_example_tags() -> list[dict]:
    """用户反馈的机械打标序列（前 12 章）。"""
    types = [
        "progress", "small_win", "big_win", "progress",
        "small_win", "small_win", "progress", "progress",
        "small_win", "big_win", "progress", "small_win",
    ]
    notes = [
        "开局建立处境", "金手指首次效果", "首次打脸", "加压铺垫",
        "小胜连击", "势力试探", "矿场蛰伏", "收服人心",
        "禁地夺宝", "宗门大比", "清算余波", "留种",
    ]
    return [{"ch": i + 1, "type": t, "note": n} for i, (t, n) in enumerate(zip(types, notes))]


def test_is_mechanical_tag_skeleton():
    assert is_mechanical_tag_skeleton("第1·progress → 第2·small_win")
    assert not is_mechanical_tag_skeleton("1-5密钩铺屈辱/6-8首突破/9-15首打脸")


def test_tag_vs_semantic_skeleton():
    assert is_tag_style_skeleton("1章推进/2章小爽/3章大打脸")
    assert is_semantic_narrative_skeleton("59-73章矿场蛰伏/74-93章收服人心建立势力")
    assert not is_semantic_narrative_skeleton("1章推进/2章小爽")
    from app.services.bootstrap.rhythm_pacing import needs_rhythm_skeleton_refresh
    assert needs_rhythm_skeleton_refresh("1章A/2章B/3章C/4章D")
    assert not needs_rhythm_skeleton_refresh("1-15章矿场蛰伏/16-35章收服人心")


def test_build_pacing_skeleton_compresses_segments():
    tags = _user_example_tags()
    skeleton = build_pacing_skeleton_from_tags(tags, preview_chapters=12)
    assert "第1·" not in skeleton
    assert "→" not in skeleton
    assert "开局建立处境" in skeleton or "1章" in skeleton
    assert "章推进" not in skeleton


def test_macro_skeleton_matches_vol2_style():
    from app.services.bootstrap.rhythm_pacing import build_macro_pacing_skeleton_from_tags

    tags = _user_example_tags()
    skeleton = build_macro_pacing_skeleton_from_tags(tags, planned_chapters=12, target_segments=4)
    assert "-" in skeleton
    assert skeleton.count("/") >= 2
    assert "章推进" not in skeleton
    assert "章" in skeleton


def test_repair_fixes_consecutive_dry_and_small_win():
    tags = _user_example_tags()
    repaired, notes = repair_rhythm_tags(tags)
    # 7-8 连续 progress 应被修复
    ch7 = next(t for t in repaired if t["ch"] == 7)
    ch8 = next(t for t in repaired if t["ch"] == 8)
    assert ch7["type"] != "progress" or ch8["type"] != "progress"
    # 5-6 连续 small_win 应被稀释
    ch5 = next(t for t in repaired if t["ch"] == 5)
    ch6 = next(t for t in repaired if t["ch"] == 6)
    assert not (ch5["type"] == "small_win" and ch6["type"] == "small_win")
    assert notes


def test_apply_preserves_semantic_skeleton():
    semantic = "59-73章矿场蛰伏/74-93章收服人心建立势力"
    tags = _user_example_tags()
    assert refresh_opening_volume_pacing_skeleton(semantic, tags) == semantic
    assert apply_rhythm_to_pacing_skeleton(semantic, tags) == semantic


def test_build_story_buffer_by_rule_from_face_slap_targets():
    ctx = {
        "face_slap_map": {
            "targets": [
                {
                    "name": "赵凌霄",
                    "chapter_estimate": "约第10章",
                    "slap_type": "武力碾压",
                    "slap_scene": "当众击败赵凌霄",
                },
                {
                    "name": "厉九幽",
                    "chapter_estimate": "第25章",
                    "slap_type": "财富碾压",
                    "slap_scene": "砸钱压服厉九幽",
                },
                {
                    "name": "楚惊鸿",
                    "chapter_estimate": "40",
                    "slap_type": "感情反转",
                    "slap_scene": "反转楚惊鸿态度",
                },
            ],
        },
        "golden_finger": {"upgrade_stages": [{"name": "初觉醒", "chapter_range": "第5章"}]},
    }
    buffers = _build_story_buffer_by_rule(ctx)
    assert 3 <= len(buffers) <= 5
    types = {b["satisfaction_type"] for b in buffers}
    assert len(types) >= 2
    assert all(b.get("insertion_point") for b in buffers)


def test_apply_replaces_mechanical_and_tag_style():
    for bad in (
        "第1·progress → 第2·small_win",
        "1章推进/2章小爽/3章大打脸",
    ):
        out = refresh_opening_volume_pacing_skeleton(bad, _user_example_tags(), preview_chapters=12)
        assert not is_mechanical_tag_skeleton(out)
        assert not is_tag_style_skeleton(out)
        assert "/" in out
