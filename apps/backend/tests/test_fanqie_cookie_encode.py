"""番茄 Cookie 头含 Unicode 时不应触发 ASCII 编码错误。"""

from app.services.fanqie.creds import normalize_cookie_header


def test_normalize_cookie_header_ascii_unchanged():
    raw = "sessionid=abc123; novel_web_id=xyz"
    assert normalize_cookie_header(raw) == raw


def test_normalize_cookie_header_encodes_unicode_values():
    raw = "foo=中文; bar=ok"
    out = normalize_cookie_header(raw)
    assert "中文" not in out
    assert out.encode("ascii")
    assert "foo=" in out
    assert "bar=ok" in out
