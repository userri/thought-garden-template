// 순수 함수 모음 — content/background 공용 + node --test 로 테스트.
// (content script 전역과 node 양쪽에서 동작하도록 마지막에 조건부 export)

function slugify(title, fallback) {
  const slug = title
    .replace(/[^\w가-힣]+/gu, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/g, "");
  return slug || fallback;
}

// URL에서 blogId/logNo 추출. 지원:
//   m.blog.naver.com/{blogId}/{logNo}
//   blog.naver.com/PostView.naver?blogId=..&logNo=..
function parsePostUrl(href) {
  const url = new URL(href);
  if (url.hostname === "m.blog.naver.com") {
    const m = url.pathname.match(/^\/([\w-]+)\/(\d+)$/);
    if (m) return { blogId: m[1], logNo: m[2] };
  }
  const blogId = url.searchParams.get("blogId");
  const logNo = url.searchParams.get("logNo");
  if (blogId && /^\d+$/.test(logNo || "")) return { blogId, logNo };
  return null;
}

// fetch.py의 extract_body와 동일한 우선순위
const BODY_SELECTORS = ["div.se-main-container", "div#viewTypeSelector", "div.post_ct"];

function cleanBodyText(raw) {
  return raw
    .replace(/[ \t​]+/g, " ")
    .replace(/\n\s*\n+/g, "\n\n")
    .trim();
}

function postFilename(dateStr, title, logNo) {
  return `${dateStr}-${slugify(title, logNo)}.md`;
}

function makeMarkdown({ title, date, url, body }) {
  const safeTitle = title.replace(/"/g, "'");
  return `---\ntitle: "${safeTitle}"\ndate: ${date}\nurl: ${url}\n---\n\n${body}\n`;
}

// 네이버 날짜 표기("2026. 7. 16. 23:06" / "3시간 전" 등) → YYYY-MM-DD. 실패 시 오늘.
function parseNaverDate(text, today) {
  const m = (text || "").match(/(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})/);
  if (!m) return today;
  return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
}

// 페이지 원본 HTML에서 작성일 추출. addDate(epoch ms)가 정확하고 렌더링 타이밍과
// 무관해서 1순위, 화면 표기("2026. 6. 30.")는 폴백. 못 찾으면 null.
function naverDateFromHtml(html) {
  const ms = html.match(/addDate="(\d{10,})"/i);
  if (ms) {
    // epoch은 절대시각 — KST(+9h) 기준 날짜로 변환
    return new Date(Number(ms[1]) + 9 * 3600 * 1000).toISOString().slice(0, 10);
  }
  const m = html.match(/(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\./);
  if (m) return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  return null;
}

// UTF-8 안전 base64 (GitHub contents API용)
function toBase64Utf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function fromBase64Utf8(b64) {
  const bin = atob(b64.replace(/\n/g, ""));
  return new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0)));
}

if (typeof module !== "undefined") {
  module.exports = {
    slugify,
    parsePostUrl,
    cleanBodyText,
    postFilename,
    makeMarkdown,
    parseNaverDate,
    naverDateFromHtml,
    BODY_SELECTORS,
  };
}
