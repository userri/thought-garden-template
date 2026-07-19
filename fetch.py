"""네이버 블로그 RSS에서 새 글을 발견하고, 본문 전문을 posts/에 저장한다.

RSS description은 ~500자에서 잘리므로 본문은 모바일 페이지에서 따로 가져온다.
(공개 글만 — 비공개 글은 v1 범위 밖, README 참고)
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import feedparser
import requests
from bs4 import BeautifulSoup

POSTS_DIR = Path(__file__).parent / "posts"
RSS_URL = "https://rss.blog.naver.com/{blog_id}.xml"
MOBILE_URL = "https://m.blog.naver.com/{blog_id}/{log_no}"
UA = {"User-Agent": "Mozilla/5.0 (thought-garden; personal archive bot)"}


def slugify(title: str, fallback: str) -> str:
    slug = re.sub(r"[^\w가-힣]+", "-", title).strip("-")[:40].strip("-")
    return slug or fallback


def log_no_from_guid(guid: str) -> str:
    return guid.rstrip("/").rsplit("/", 1)[-1]


def extract_body(html: str) -> str:
    """모바일 글 페이지 HTML에서 본문 텍스트를 추출한다."""
    soup = BeautifulSoup(html, "html.parser")
    container = (
        soup.select_one("div.se-main-container")  # 스마트에디터 ONE
        or soup.select_one("div#viewTypeSelector")  # 구 에디터
        or soup.select_one("div.post_ct")
    )
    if container is None:
        return ""
    text = container.get_text("\n")
    text = re.sub(r"[ \t​]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def post_filename(date: datetime, title: str, log_no: str) -> str:
    return f"{date:%Y-%m-%d}-{slugify(title, log_no)}.md"


def make_markdown(title: str, date: datetime, url: str, body: str) -> str:
    safe_title = title.replace('"', "'")
    return (
        f"---\n"
        f'title: "{safe_title}"\n'
        f"date: {date:%Y-%m-%d}\n"
        f"url: {url}\n"
        f"---\n\n{body}\n"
    )


def existing_log_nos() -> set:
    nos = set()
    for p in POSTS_DIR.glob("*.md"):
        m = re.search(r"^url: .*/(\d+)\s*$", p.read_text(encoding="utf-8"), re.M)
        if m:
            nos.add(m.group(1))
    return nos


def fetch(blog_id: str) -> list:
    POSTS_DIR.mkdir(exist_ok=True)
    feed = feedparser.parse(RSS_URL.format(blog_id=blog_id))
    if feed.bozo and not feed.entries:
        sys.exit(f"RSS를 읽지 못했습니다: {feed.bozo_exception}")
    seen = existing_log_nos()
    saved = []
    for entry in feed.entries:
        log_no = log_no_from_guid(entry.guid)
        if log_no in seen:
            continue
        date = datetime(*entry.published_parsed[:6])
        url = f"https://blog.naver.com/{blog_id}/{log_no}"
        resp = requests.get(MOBILE_URL.format(blog_id=blog_id, log_no=log_no), headers=UA, timeout=30)
        body = extract_body(resp.text) if resp.ok else ""
        if not body:
            # 본문 추출 실패 시 RSS 요약이라도 남긴다 (유실 방지)
            body = BeautifulSoup(entry.description, "html.parser").get_text(" ").strip()
        path = POSTS_DIR / post_filename(date, entry.title, log_no)
        path.write_text(make_markdown(entry.title, date, url, body), encoding="utf-8")
        saved.append(path)
        print(f"saved: {path.name}")
    if not saved:
        print("새 글 없음")
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--blog-id", required=True)
    fetch(parser.parse_args().blog_id)
