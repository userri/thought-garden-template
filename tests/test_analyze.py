from datetime import date

import pytest

import analyze


def test_report_path_iso_week():
    assert analyze.report_path(date(2026, 7, 16)).name == "2026-29.md"


def test_report_path_year_boundary():
    # 2027-01-01은 ISO 기준 2026년 53주
    assert analyze.report_path(date(2027, 1, 1)).name == "2026-53.md"


def test_build_messages_contains_rules_and_corpus():
    msgs = analyze.build_messages("일기 본문")
    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert "원문 문장 인용 필수" in content
    assert "<posts>\n일기 본문\n</posts>" in content


def test_load_posts_empty_exits(tmp_path):
    with pytest.raises(SystemExit):
        analyze.load_posts(tmp_path)


def test_load_posts_joins_sorted(tmp_path):
    (tmp_path / "2026-07-02-b.md").write_text("둘", encoding="utf-8")
    (tmp_path / "2026-07-01-a.md").write_text("하나", encoding="utf-8")
    assert analyze.load_posts(tmp_path) == "하나\n\n=====\n\n둘"


class FakeBlock:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


def test_extract_text_skips_thinking_blocks():
    blocks = [FakeBlock("thinking", thinking="..."), FakeBlock("text", text="리포트")]
    assert analyze.extract_text(blocks) == "리포트"


def test_extract_text_no_text_exits():
    with pytest.raises(SystemExit):
        analyze.extract_text([FakeBlock("thinking", thinking="...")])


def test_report_path_private_prefix():
    assert analyze.report_path(date(2026, 7, 16), "private-").name == "private-2026-29.md"


def test_build_cross_messages_wraps_both_corpora():
    content = analyze.build_cross_messages("공개글", "비밀글")[0]["content"]
    assert "<public>\n공개글\n</public>" in content
    assert "<private>\n비밀글\n</private>" in content
    assert "양쪽 모두 인용" in content


def test_cross_report_prefix_matches_sparse_exclusion():
    # 교차 리포트도 비공개 내용을 담으므로 private-* 패턴에 걸려야 한다
    assert analyze.report_path(date(2026, 7, 16), "private-cross-").name.startswith("private-")
