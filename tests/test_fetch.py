from datetime import datetime

import fetch


def test_slugify_korean_title():
    assert fetch.slugify("블로그 유기 안함요", "123") == "블로그-유기-안함요"


def test_slugify_special_chars_fallback():
    assert fetch.slugify("!!!???", "224331671749") == "224331671749"


def test_slugify_truncates():
    assert len(fetch.slugify("가" * 100, "x")) <= 40


def test_log_no_from_guid():
    assert fetch.log_no_from_guid("https://blog.naver.com/jokebear67/224331671749") == "224331671749"


def test_extract_body_smart_editor():
    html = '<html><body><div class="se-main-container"><p>첫 줄</p><p>둘째  줄</p></div></body></html>'
    assert fetch.extract_body(html) == "첫 줄\n둘째 줄"


def test_extract_body_missing_container():
    assert fetch.extract_body("<html><body><p>없음</p></body></html>") == ""


def test_post_filename():
    d = datetime(2026, 7, 16)
    assert fetch.post_filename(d, "테스트 글", "999") == "2026-07-16-테스트-글.md"


def test_make_markdown_frontmatter():
    md = fetch.make_markdown("제목 \"따옴표\"", datetime(2026, 7, 16), "https://x/1", "본문")
    assert md.startswith("---\n")
    assert "title: \"제목 '따옴표'\"" in md
    assert "date: 2026-07-16" in md
    assert "url: https://x/1" in md
    assert md.rstrip().endswith("본문")


def test_existing_log_nos(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch, "POSTS_DIR", tmp_path)
    (tmp_path / "a.md").write_text("---\nurl: https://blog.naver.com/x/111\n---\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("no url here", encoding="utf-8")
    assert fetch.existing_log_nos() == {"111"}
