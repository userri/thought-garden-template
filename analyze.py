"""posts/ 전체를 분석 프롬프트(v3)로 Anthropic API에 보내 주간 리포트를 만든다.

--private: private-posts/를 분석해 reports/private-YYYY-WW.md 생성 (수동 실행 전용).
공개/비공개는 톤이 달라 분리 분석한다 — README 참고.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).parent
POSTS_DIR = BASE / "posts"
REPORTS_DIR = BASE / "reports"
# 마지막으로 분석한 코퍼스의 지문. 새 글이 없으면 같은 내용을 또 분석하는 낭비를 막는다.
FINGERPRINT_PATH = REPORTS_DIR / ".corpus.json"

# 기본 Haiku — 단독 리포트는 Sonnet과 품질 차이를 체감 못해 저가 모델로 굳힘 (2026-07 실사용 비교).
# 교차 분석은 코퍼스 합산이 Haiku 컨텍스트(200k)를 넘어 Sonnet 필수 — 워크플로에서 지정.
MODEL = os.environ.get("TG_MODEL", "claude-haiku-4-5")

# v3 — 실제 글 6편으로 2사이클 검증. 각 규칙의 유래는 README '"AI 출력 검증' 섹션 참고.
PROMPT_V3 = """당신은 개인 일기 아카이브의 관찰자입니다. 아래 글들을 읽고 다음 3종을 출력하세요.

① 글별 한 줄 요약
② 반복 패턴
③ 시간에 따른 변화

규칙 (반드시 준수):
1. 모든 인사이트는 원문 문장 인용 필수. 근거 없는 평가("성장했네요" 등) 금지.
2. 원인/심리 추정 금지. 관찰만 기술. 해석은 글쓴이의 몫.
3. 패턴으로 묶기 전, 글쓴이 본인이 다른 설명을 했는지 확인하고 그 설명을 존중할 것.
4. 당연한 반복(생일, 계절 등 정보가치 없는 항목)은 제외.
5. 본인 진술로만 존재하고 원문 기록이 없는 과거사는 "기록 미확인"을 명시. 정황이 강해도 단정하지 말 것.
6. 3개 이상 시점에서 등장해야 "패턴". 2개 시점이면 "후보"로만 표기.

출력은 한국어 마크다운으로.
"""

# 교차(공개 vs 비공개) 분석 — 섞지 않고 대조한다. 규칙은 v3 공통 + 교차 전용 2개.
PROMPT_CROSS = """당신은 개인 일기 아카이브의 관찰자입니다. 같은 사람이 쓴 글이
<public>(공개 블로그)과 <private>(비공개 일기)로 나뉘어 있습니다. 두 기록을 대조해
다음 3종을 출력하세요.

① 같은 시기의 공개/비공개 대비 — 같은 시기를 다르게 기록한 사례
② 한쪽에만 존재하는 주제 — 공개에만 쓰는 것 / 비공개에만 쓰는 것
③ 같은 사건의 두 기록 — 동일 사건이 양쪽에 있으면 서술 차이를 나란히

규칙 (반드시 준수):
1. 모든 인사이트는 원문 문장 인용 필수. 대비 사례는 반드시 양쪽 모두 인용.
2. 원인/심리 추정 금지. "숨기고 싶어서" 같은 동기 해석 금지. 차이의 존재만 기술.
3. 패턴으로 묶기 전, 글쓴이 본인이 다른 설명을 했는지 확인하고 그 설명을 존중할 것.
4. 당연한 차이(공개글이 더 정제됨, 비속어가 비공개에 많음 등)는 제외.
5. 시기 추정이 불확실하면 "시기 불확실"을 명시하고 대비 사례로 쓰지 말 것.
6. 3개 이상 시점에서 등장해야 "패턴". 2개 시점이면 "후보"로만 표기.

출력은 한국어 마크다운으로.
"""


# 회상 리포트 — 지난 해들의 '이맘때' 글을 날짜로 뽑아 지금과 대조한다.
# 전체 분석은 글이 쌓일수록 개별 글이 패턴으로 뭉개져 사라지므로, 발견은 따로 만든다.
RECALL_WINDOW_DAYS = 10  # 오늘 기준 ±10일 = "이번 주 무렵"
RECALL_RECENT_N = 3  # 대조 기준이 되는 최근 글 수

PROMPT_RECALL = """당신은 개인 일기 아카이브의 관찰자입니다.
<past>는 지난 해들의 '이맘때' 기록이고, <now>는 최근 기록입니다.
두 시점을 대조해 다음 3종을 출력하세요.

① 그때 무엇을 쓰고 있었나 — 연도별 한 줄 요약
② 그때와 지금 — 같은 소재·관심사가 어떻게 달라졌는지
③ 그때만 있고 지금은 없는 것 / 지금만 있는 것

규칙 (반드시 준수):
1. 모든 인사이트는 원문 문장 인용 필수. 대비 사례는 그때와 지금 양쪽 모두 인용.
2. 원인/심리 추정 금지. 관찰만 기술. 해석은 글쓴이의 몫.
3. 묶기 전, 글쓴이 본인이 다른 설명을 했는지 확인하고 그 설명을 존중할 것.
4. 당연한 차이(나이가 들었다, 계절이 같다 등)는 제외.
5. 기록이 없는 해는 "기록 없음"으로 명시하고 추측하지 말 것.
6. 3개 이상 연도에서 나타나야 "패턴". 2개면 "후보"로만 표기.

출력은 한국어 마크다운으로.
"""


def post_date(path: Path):
    """파일명 앞의 YYYY-MM-DD에서 작성일 추출. 없으면 None."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})-", path.name)
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def day_distance(a: date, b: date) -> int:
    """연도를 무시한 '몇 월 며칠'끼리의 거리 (연말↔연초 감김 처리)."""
    diff = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(diff, 365 - diff)


def all_post_paths() -> list:
    dirs = [POSTS_DIR, BASE / "private-posts"]
    return [p for d in dirs if d.exists() for p in d.glob("*.md")]


def select_recall(paths: list, today: date, window: int = RECALL_WINDOW_DAYS,
                  recent_n: int = RECALL_RECENT_N):
    """(지난 해들의 이맘때 글, 최근 글) — 날짜만으로 고른다. LLM 불필요."""
    dated = sorted((d, p) for d, p in ((post_date(p), p) for p in paths) if d)
    past = [
        (d, p) for d, p in dated
        if d.year < today.year and day_distance(d, today) <= window
    ]
    return past, dated[-recent_n:]


def build_recall_corpus(past: list, recent: list) -> str:
    def block(items):
        return "\n\n=====\n\n".join(
            f"[{d.year}]\n{p.read_text(encoding='utf-8')}" for d, p in items
        )

    return f"<past>\n{block(past)}\n</past>\n\n<now>\n{block(recent)}\n</now>"


def build_recall_messages(corpus: str) -> list:
    return [{"role": "user", "content": f"{PROMPT_RECALL}\n\n{corpus}"}]


def load_posts(posts_dir: Path = POSTS_DIR) -> str:
    posts = sorted(posts_dir.glob("*.md"))
    if not posts:
        sys.exit(f"{posts_dir.name}/가 비어 있습니다. fetch.py를 먼저 실행하세요.")
    return "\n\n=====\n\n".join(p.read_text(encoding="utf-8") for p in posts)


def today_kst(now=None) -> date:  # now: datetime | None (3.9 로컬 호환 위해 무표기)
    """주차 계산 기준일. CI 러너는 UTC라 KST 월요일 새벽이 아직 지난주로 잡힌다."""
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("Asia/Seoul")).date()


def report_path(today: date, prefix: str = "") -> Path:
    year, week, _ = today.isocalendar()
    return REPORTS_DIR / f"{prefix}{year}-{week:02d}.md"


def build_messages(corpus: str) -> list:
    return [{"role": "user", "content": f"{PROMPT_V3}\n\n<posts>\n{corpus}\n</posts>"}]


def build_cross_messages(public: str, private: str) -> list:
    return [{
        "role": "user",
        "content": (
            f"{PROMPT_CROSS}\n\n<public>\n{public}\n</public>\n\n"
            f"<private>\n{private}\n</private>"
        ),
    }]


def extract_text(content_blocks) -> str:
    """응답에서 텍스트 블록만 모은다 (thinking 블록이 섞여 올 수 있음)."""
    texts = [b.text for b in content_blocks if getattr(b, "type", "") == "text"]
    if not texts:
        sys.exit("응답에 텍스트 블록이 없습니다.")
    return "\n".join(texts)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_fingerprints() -> dict:
    if not FINGERPRINT_PATH.exists():
        return {}
    try:
        return json.loads(FINGERPRINT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}  # 손상 시 그냥 다시 분석한다 — 리포트 생성을 막을 이유는 없다


def save_fingerprint(mode: str, digest: str) -> None:
    marks = load_fingerprints()
    marks[mode] = digest
    REPORTS_DIR.mkdir(exist_ok=True)
    FINGERPRINT_PATH.write_text(
        json.dumps(marks, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def analyze(mode: str = "public", force: bool = False):
    import anthropic

    if mode == "cross":
        public, private = load_posts(POSTS_DIR), load_posts(BASE / "private-posts")
        messages = build_cross_messages(public, private)
        corpus = public + private
        prefix = "private-cross-"  # private-* 로 시작해야 로컬 sparse-checkout 제외에 걸림
    elif mode == "recall":
        past, recent = select_recall(all_post_paths(), today_kst())
        if not past:
            print("skip: 이맘때 과거 글이 없음 — 회상할 게 없다")
            return None
        corpus = build_recall_corpus(past, recent)
        messages = build_recall_messages(corpus)
        prefix = "private-recall-"  # 비공개 글을 포함하므로 private-* 규칙을 따른다
        print(f"회상 대상: 과거 {len(past)}편 ({sorted({d.year for d, _ in past})}) vs 최근 {len(recent)}편")
    else:
        corpus = load_posts(BASE / "private-posts" if mode == "private" else POSTS_DIR)
        messages = build_messages(corpus)
        prefix = "private-" if mode == "private" else ""

    digest = fingerprint(corpus)
    if not force and load_fingerprints().get(mode) == digest:
        print(f"skip: 새 글 없음 — {mode} 코퍼스가 지난 분석과 동일 (--force로 강제 실행)")
        return None

    client = anthropic.Anthropic()
    # max_tokens는 thinking + 본문 합산 한도. 코퍼스가 크면 thinking만 수만 토큰을 쓰므로
    # 넉넉히 잡고, 이 크기는 HTTP 타임아웃을 피하려면 스트리밍이 필요하다.
    with client.messages.stream(
        model=MODEL,
        max_tokens=64000,
        messages=messages,
    ) as stream:
        resp = stream.get_final_message()
    if resp.stop_reason == "max_tokens":
        print("경고: max_tokens 도달 (리포트가 잘렸을 수 있음)", file=sys.stderr)
    REPORTS_DIR.mkdir(exist_ok=True)
    # CI 러너는 UTC — KST 월요일 아침 실행 시 UTC는 아직 일요일(지난 주차)이라
    # 지난주 리포트를 덮어쓰는 버그가 있었다. 주차 계산은 항상 KST 기준.
    path = report_path(today_kst(), prefix)
    path.write_text(extract_text(resp.content) + "\n", encoding="utf-8")
    save_fingerprint(mode, digest)
    print(f"saved: {path.name}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--private", action="store_true", help="private-posts/ 분석")
    group.add_argument("--cross", action="store_true", help="공개 vs 비공개 교차 분석")
    group.add_argument("--recall", action="store_true", help="지난 해들의 이맘때 vs 지금")
    parser.add_argument("--force", action="store_true", help="새 글이 없어도 강제 분석")
    args = parser.parse_args()
    mode = (
        "cross" if args.cross
        else "recall" if args.recall
        else "private" if args.private
        else "public"
    )
    analyze(mode=mode, force=args.force)
