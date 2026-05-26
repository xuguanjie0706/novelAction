"""consistency_fix_service 单元测试（无 LLM 调用）。"""

from types import SimpleNamespace

from app.services.consistency_fix_service import (
    EntityCodebook,
    _rule_faction_rename_patches,
    _rule_realm_patches,
    build_fix_prompt,
)


def test_entity_codebook_resolve():
    chars = [SimpleNamespace(name="叶辰", faction="叶家", current_realm="印徒")]
    facs = [SimpleNamespace(name="青云城林家")]
    skills = [SimpleNamespace(name="万古镇狱诀", mastered_by="")]
    book = EntityCodebook(chars, facs, skills)
    assert book.resolve_entity_name("character", "C0") == "叶辰"
    assert book.resolve_entity_name("faction", "F0") == "青云城林家"
    assert "C0" in build_fix_prompt([(0, {"type": "faction_mismatch"})], book)[1]


def test_rule_faction_rename_from_curly_quotes():
    facs = [SimpleNamespace(name="青云城林家")]
    pairs = [
        (
            1,
            {
                "type": "faction_mismatch",
                "suggestion": "将势力档案及卷描述中的\u201c林家\u201d统一更正为\u201c叶家\u201d。",
            },
        ),
    ]
    patches = _rule_faction_rename_patches(pairs, facs)
    assert len(patches) == 1
    assert patches[0]["new_value"] == "青云城叶家"
    assert patches[0]["field"] == "name"


def test_rule_realm_from_suggestion():
    chars = [
        SimpleNamespace(name="厉风", current_realm="印士"),
        SimpleNamespace(name="柳红衣", current_realm="印士"),
    ]
    pairs = [
        (
            2,
            {
                "type": "realm_mismatch",
                "description": "后期反派厉风、柳红衣仅为印士（2阶），严重低于卷轴剧情逻辑。",
                "suggestion": "将中后期反派境界提升至皇印境（6阶）或以上。",
            },
        ),
    ]
    patches = _rule_realm_patches(pairs, chars)
    assert len(patches) == 2
    assert {p["new_value"] for p in patches} == {"皇印境"}


def test_rule_realm_shewei_and_biaozhu_patterns():
    chars = [
        SimpleNamespace(name="莫沧", current_realm="灵尊境"),
        SimpleNamespace(name="韩厉", current_realm="战卒"),
    ]
    pairs = [
        (
            18,
            {
                "type": "realm_mismatch",
                "description": "莫沧(灵尊境)作为最终BOSS，未达到境界体系上限虚神境",
                "suggestion": "将莫沧终局境界设为虚神境",
            },
        ),
        (
            19,
            {
                "type": "realm_mismatch",
                "description": "韩厉境界标注为战卒，与主轴境界体系名称不一致",
                "suggestion": "参照主轴统一标注为灵徒境",
            },
        ),
    ]
    patches = _rule_realm_patches(pairs, chars)
    by_name = {p["entity_name"]: p["new_value"] for p in patches}
    assert by_name.get("莫沧") == "虚神境"
    assert by_name.get("韩厉") == "灵徒境"


def test_rule_realm_jingjie_zhi_pattern():
    chars = [SimpleNamespace(name="柳红衣", current_realm="印士")]
    pairs = [
        (
            4,
            {
                "type": "villain_alignment",
                "description": "柳红衣以印士境界重塑中州皇权。",
                "suggestion": "提升柳红衣境界至宗印境，使其具备统治中州的实力背景。",
            },
        ),
    ]
    patches = _rule_realm_patches(pairs, chars)
    assert len(patches) == 1
    assert patches[0]["new_value"] == "宗印境"
