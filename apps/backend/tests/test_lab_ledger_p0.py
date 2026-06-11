"""lab 台账 P0：见证者别名 / 资产去噪 / 境界解析。"""
from app.services.dabai.lab_ledger import (
    _is_noise_asset,
    _parse_sub_realm_label,
    _relation_visible,
)
from app.services.dabai.lab_quality import _witness_in_content


def test_witness_alias_matches_generic_terms():
    content = "周围聚集了不少杂役和路过的家仆，纷纷惊呼。"
    assert _witness_in_content("围观家奴", content)
    assert _witness_in_content("叶家弟子", "几名族人咽了口唾沫，满脸不可思议。")


def test_noise_asset_filtered():
    assert _is_noise_asset("修为点")
    assert _is_noise_asset("修为点300")
    assert not _is_noise_asset("蛮牛劲（残缺）")


def test_parse_sub_realm_from_tail():
    text = "当前境界：淬体境四重！全场死寂。"
    assert _parse_sub_realm_label(text) == "淬体境四重"


def test_dormant_seed_relation_hidden():
    class Rel:
        to_name = "林梦瑶"
        last_change_chapter = 0
        source = "seed"

    assert not _relation_visible(Rel(), appeared={"苏清月", "叶天"}, on_stage=set())
    assert _relation_visible(Rel(), appeared={"林梦瑶"}, on_stage=set())
