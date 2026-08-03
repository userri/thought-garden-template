from datetime import date, datetime, timezone

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


def test_fingerprint_deterministic_and_sensitive():
    assert analyze.fingerprint("글") == analyze.fingerprint("글")
    assert analyze.fingerprint("글") != analyze.fingerprint("글!")


def test_fingerprint_roundtrip_and_corruption(tmp_path, monkeypatch):
    monkeypatch.setattr(analyze, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(analyze, "FINGERPRINT_PATH", tmp_path / ".corpus.json")
    assert analyze.load_fingerprints() == {}
    analyze.save_fingerprint("public", "abc")
    analyze.save_fingerprint("private", "def")
    assert analyze.load_fingerprints() == {"public": "abc", "private": "def"}
    (tmp_path / ".corpus.json").write_text("{망가짐", encoding="utf-8")
    assert analyze.load_fingerprints() == {}  # 손상돼도 죽지 않고 재분석


def test_analyze_skips_when_corpus_unchanged(tmp_path, monkeypatch):
    posts, reports = tmp_path / "posts", tmp_path / "reports"
    posts.mkdir(), reports.mkdir()
    (posts / "2026-07-01-a.md").write_text("하나", encoding="utf-8")
    monkeypatch.setattr(analyze, "POSTS_DIR", posts)
    monkeypatch.setattr(analyze, "REPORTS_DIR", reports)
    monkeypatch.setattr(analyze, "FINGERPRINT_PATH", reports / ".corpus.json")

    corpus = analyze.load_posts(posts)
    analyze.save_fingerprint("public", analyze.fingerprint(corpus))
    # API 클라이언트를 만들면 테스트가 실패하도록 막아둔다 (호출 = 낭비)
    monkeypatch.setattr(
        analyze, "extract_text", lambda _: pytest.fail("API를 호출하면 안 된다")
    )
    assert analyze.analyze(mode="public") is None

    # 새 글이 생기면 다시 분석해야 한다 (지문 불일치)
    (posts / "2026-07-02-b.md").write_text("둘", encoding="utf-8")
    assert analyze.fingerprint(analyze.load_posts(posts)) != analyze.load_fingerprints()["public"]


def test_today_kst_uses_seoul_not_utc():
    # 실제 사고 재현: 2026-07-26 22:53Z 실행 = KST 07-27(월, 31주차).
    # UTC 기준이면 07-26(일, 30주차)이 되어 지난주 리포트를 덮어썼다.
    run_at = datetime(2026, 7, 26, 22, 53, tzinfo=timezone.utc)
    assert analyze.today_kst(run_at) == date(2026, 7, 27)
    assert analyze.report_path(analyze.today_kst(run_at)).name == "2026-31.md"


def test_post_date_from_filename():
    from pathlib import Path
    assert analyze.post_date(Path("2021-03-20-3월-19일의-일기.md")) == date(2021, 3, 20)
    assert analyze.post_date(Path("no-date.md")) is None


def test_day_distance_wraps_around_new_year():
    assert analyze.day_distance(date(2021, 7, 27), date(2026, 7, 27)) == 0
    assert analyze.day_distance(date(2021, 7, 20), date(2026, 7, 27)) == 7
    # 12/30과 1/2는 3일 거리 (연도 경계를 넘어도 가까움)
    assert analyze.day_distance(date(2021, 12, 30), date(2026, 1, 2)) <= 4


def test_select_recall_picks_past_years_near_today(tmp_path):
    names = [
        "2021-07-25-과거-근처.md",   # 이맘때, 과거 → 뽑힘
        "2023-07-30-과거-근처2.md",  # 이맘때, 과거 → 뽑힘
        "2022-01-05-과거-먼날.md",   # 과거지만 시기 다름 → 제외
        "2026-07-26-올해-최근.md",   # 올해 → past에서 제외, recent에는 포함
    ]
    for n in names:
        (tmp_path / n).write_text(n, encoding="utf-8")
    past, recent = analyze.select_recall(
        list(tmp_path.glob("*.md")), date(2026, 7, 27), recent_n=2
    )
    assert sorted(d.year for d, _ in past) == [2021, 2023]
    assert recent[-1][0] == date(2026, 7, 26)  # 최근 글이 마지막


def test_recall_corpus_and_prompt_shape(tmp_path):
    (tmp_path / "2021-07-25-a.md").write_text("옛날 글", encoding="utf-8")
    (tmp_path / "2026-07-26-b.md").write_text("요즘 글", encoding="utf-8")
    past, recent = analyze.select_recall(
        list(tmp_path.glob("*.md")), date(2026, 7, 27), recent_n=1
    )
    corpus = analyze.build_recall_corpus(past, recent)
    assert "<past>" in corpus and "[2021]" in corpus and "옛날 글" in corpus
    assert "<now>" in corpus and "요즘 글" in corpus
    content = analyze.build_recall_messages(corpus)[0]["content"]
    assert "그때와 지금" in content and "양쪽 모두 인용" in content


def test_recall_report_stays_private():
    # 회상 리포트는 비공개 글을 포함하므로 sparse-checkout 제외 패턴에 걸려야 한다
    assert analyze.report_path(date(2026, 7, 27), "private-recall-").name.startswith("private-")


def test_is_out_of_credit_distinguishes_billing_from_bugs():
    # 실제 응답 메시지 (2026-08-03 private report 실패)
    billing = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
               "'message': 'Your credit balance is too low to access the Anthropic API.'}}")
    assert analyze.is_out_of_credit(billing)
    # 진짜 버그성 400은 실패로 남아야 한다
    assert not analyze.is_out_of_credit("prompt is too long: 211682 tokens > 200000 maximum")


class FakeUsage:
    input_tokens = 88_000
    output_tokens = 8_000


def test_usage_footer_computes_cost():
    footer = analyze.usage_footer("claude-haiku-4-5", FakeUsage())
    assert "입력 88,000" in footer and "출력 8,000" in footer
    # 88k/1M*$1 + 8k/1M*$5 = 0.088 + 0.040 = $0.128
    assert "$0.128" in footer


def test_usage_footer_unknown_model_shows_tokens_only():
    footer = analyze.usage_footer("gpt-x", FakeUsage())
    assert "88,000" in footer and "$" not in footer
