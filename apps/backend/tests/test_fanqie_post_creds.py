"""番茄 POST 凭据校验与 cURL 解析。"""

import pytest

from app.services.fanqie.creds import (
    build_creds_from_curl_text,
    ensure_fanqie_post_creds,
    extract_a_bogus,
    extract_csrf_token,
    extract_ms_token,
    extract_post_body_fields,
    merge_creds_from_curl,
    sanitize_cookie_input,
)

SAMPLE_COVER_ARTICLE_CURL = """curl 'https://fanqienovel.com/api/author/article/cover_article/v0/?msToken=T33AgpGd-903wOPRTXWamBWw_Hz4SVa1CIAcWI0M791ocdY66j4zZ7bWOQYuodlLyTA1hTy4NewP7TQeWPAORtra36_SjrGRyte5zOiGyvQIuJWJaHLuKtlWFfTXWoexFanIckwY6b6JiJALNPXKnyv7W9xB_34F4tlfxMVkbQ1TN1as9NJrWMQ%3D&a_bogus=my4RheXwmN8VP3CSYcm-71qUK8jArP8yweiORiTC7xOOPZFc15BWBGajcqNVtsjuEWBRwCd7-VaxGEEOYufbA9ppKmkDSxif2mO5IhmLM1wvTMhmLNRFeL8x9JeGWmiEu%2FKyJAgX1U%2FP2EA4LZakUdAJHAPNsOip%2FraRdcWaT9efgMs90ZMMPuXWjDSe0a3h%2FG0RHib%3D' \\
  -b 'novel_web_id=7610770754896479778; sessionid=6b643e169edba694f07b03516924f1f8' \\
  -H 'x-secsdk-csrf-token: 000100000001a4d7fdf3d6e093248af2c60393eb6486b6e60e0e2d6bc0d30c4e63cb6129246418b37d9bc12e29aa' \\
  --data-raw 'aid=2503&app_name=muye_novel&book_id=7610780431444610073&item_id=7644631132352283198&title=%E7%AC%AC3%E7%AB%A0&content=%3Cp%3Etest%3C%2Fp%3E&volume_name=%E7%AC%AC%E4%BA%8C%E5%8D%B7&volume_id=7611074916896476185'"""
from app.services.fanqie.creds import extract_referer_enter_from
from app.services.fanqie.publish import _draft_editor_referer

SAMPLE_NEW_CHAPTER_CURL = """curl 'https://fanqienovel.com/api/author/article/cover_article/v0/?msToken=x&a_bogus=y' \\
  -H 'referer: https://fanqienovel.com/main/writer/7636438734480608281/publish/7644640370067784254?enter_from=newchapter_0' \\
  --data-raw 'aid=2503&app_name=muye_novel&book_id=7636438734480608281&item_id=7644640370067784254&title=%E7%AC%AC1%E7%AB%A0&content=%3Cp%3E321%3C%2Fp%3E&volume_name=%E7%AC%AC%E4%B8%80%E5%8D%B7%EF%BC%9A%E9%BB%98%E8%AE%A4&volume_id=7636438737206905881'"""

SAMPLE_SAVE_HISTORY_CURL = """curl 'https://fanqienovel.com/api/author/article/save_doc_history/v0/?msToken=O8MnRvSO5vPeWXbHQ9d-OhMJMgTZ94Pqy4ZILQf5k3TPVYHMGZKG0ABiZ42LOOopkrhtjgInsrGNAkUkDcAre9i7jSGDd0UrsBTyXUo1qoQM7HGz0ztuDZaSA7VtSqUINhPhTq_6QEklj41AImsMu5EA5nIFEJvt60lF3mjYGZssGNTVYkr7MCs%3D&a_bogus=DX4VgHWiQ2mcapCb8cma71BUToD%2FrP8yDMiKbNYSS5czPhMOJKBbP9qunoFdhcGEgRpbw9NH3VSicfETmu-HUCnpwskDSN4SoRxAI8Xo81iDTM7mDrRNez0ESJtGWmJEmAKRJlg1WU8a2E%2F4g3rwUp5rSAPN4OipQHrWdcRaP9tv6zG901ZBPLvWjDSCUaH0KSIbtj%3D%3D' \\
  -b 'novel_web_id=7610770754896479778; sessionid=6b643e169edba694f07b03516924f1f8' \\
  -H 'x-secsdk-csrf-token: 0001000000017e81f5bcce4786c34d7d68e94489451a8fb65128efe865d0bdc4572ab4b7e09918b3731a6db990c1' \\
  --data-raw 'aid=2503&app_name=muye_novel&book_id=7610780431444610073&item_id=7644581523210895934'"""


def test_ensure_fanqie_post_creds_requires_signature():
    with pytest.raises(ValueError, match="msToken"):
        ensure_fanqie_post_creds({"cookies": "sessionid=abc"})


def test_ensure_fanqie_post_creds_ok():
    ensure_fanqie_post_creds({
        "cookies": "sessionid=abc",
        "ms_token": "ms123",
        "a_bogus": "bogus456",
    })


def test_parse_save_doc_history_curl_extracts_signature():
    assert extract_ms_token(SAMPLE_SAVE_HISTORY_CURL).startswith("O8MnRvSO5vPeWXb")
    assert extract_a_bogus(SAMPLE_SAVE_HISTORY_CURL).startswith("DX4VgHWiQ2mcapCb")
    assert extract_csrf_token(SAMPLE_SAVE_HISTORY_CURL).startswith("0001000000017e81")
    assert "sessionid=" in sanitize_cookie_input(SAMPLE_SAVE_HISTORY_CURL)


def test_merge_creds_from_save_doc_history_curl():
    merged = merge_creds_from_curl({"cookies": "old=1"}, SAMPLE_SAVE_HISTORY_CURL)
    assert merged["ms_token"]
    assert merged["a_bogus"]
    assert merged["csrf_token"]
    assert "sessionid=" in merged["cookies"]


def test_draft_editor_referer_matches_fanqie_ui():
    url = _draft_editor_referer("7610780431444610073", "7644581523210895934")
    assert "/publish/7644581523210895934" in url
    assert "enter_from=newdraft" in url

    url_new = _draft_editor_referer(
        "7636438734480608281", "7644640370067784254", enter_from="newchapter_0",
    )
    assert "enter_from=newchapter_0" in url_new


def test_extract_referer_enter_from_newchapter():
    assert extract_referer_enter_from(SAMPLE_NEW_CHAPTER_CURL) == "newchapter_0"


def test_build_creds_from_cover_article_curl():
    creds = build_creds_from_curl_text(SAMPLE_COVER_ARTICLE_CURL)
    assert creds["ms_token"].startswith("T33AgpGd-903wOPRTXWamBWw")
    assert creds["a_bogus"].startswith("my4RheXwmN8VP3CSYcm")
    assert creds["csrf_token"].startswith("000100000001a4d7")
    assert creds["default_book_id"] == "7610780431444610073"
    assert creds["default_volume_id"] == "7611074916896476185"
    assert "第二卷" in creds["default_volume_name"]


def test_extract_post_body_fields_from_cover_article():
    fields = extract_post_body_fields(SAMPLE_COVER_ARTICLE_CURL)
    assert fields["book_id"] == "7610780431444610073"
    assert fields["item_id"] == "7644631132352283198"
    assert fields["volume_id"] == "7611074916896476185"
