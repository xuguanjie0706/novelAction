"""character_naming 命名约束与弱名检测。"""

from app.services.bootstrap.prompts.character_naming import (
    character_naming_constraints_for_prompt,
    is_weak_character_name,
)


def test_is_weak_character_name_catches_er_suffix():
    assert is_weak_character_name("灵儿") == "命中高频模板名「灵儿」"
    assert is_weak_character_name("韩灵儿") == "乳名式组合「韩灵儿」"
    assert is_weak_character_name("沈烬") is None


def test_is_weak_character_name_catches_generic_single_given():
    assert is_weak_character_name("林灵") is not None
    assert is_weak_character_name("顾远山") is None


def test_naming_prompt_includes_theme_and_existing_names():
    block = character_naming_constraints_for_prompt(
        "仙侠",
        project_title="烬天录",
        theme="复仇与救赎",
        logline="少年从灰烬中重生",
        existing_names=["沈烬", "顾远山"],
        require_name_meaning=True,
    )
    assert "烬天录" in block
    assert "复仇与救赎" in block
    assert "沈烬" in block
    assert "name_meaning" in block
    assert "灵儿" in block or "儿化" in block
