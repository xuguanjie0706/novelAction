"""dabai 非系统文（法器流）检测与 prompt 分支。"""

from dabai.non_system import (
    benchmark_non_system_note,
    golden_finger_extra_block,
    golden_finger_json_fields,
    prefers_non_system,
    prose_system_taboo_block,
)


def test_prefers_non_system_from_logline():
    assert prefers_non_system({
        "logline": "魔门收尸弟子得万魂幡，不要系统面板无叮提示",
    })
    assert not prefers_non_system({
        "logline": "废柴少年觉醒吞噬系统，一路逆袭打脸天才",
    })


def test_prefers_non_system_from_taboo():
    assert prefers_non_system({
        "logline": "少年得魔幡",
        "positioning": {"taboo_lines": ["禁止系统 UI", "不许叮"]},
    })


def test_prefers_non_system_from_golden_finger_type():
    assert prefers_non_system({
        "logline": "x",
        "golden_finger": {"type": "血炼魔器 + 魔经残篇"},
    })


def test_artifact_prompt_blocks_non_empty():
    assert "禁止" in golden_finger_extra_block()
    assert "manifestation_style" in golden_finger_json_fields(artifact=True)[1]
    assert "signature_lines" in golden_finger_json_fields(artifact=False)[1]
    assert "系统面板" in benchmark_non_system_note("魔门万魂幡，不要系统")
    assert "叮" in prose_system_taboo_block()
