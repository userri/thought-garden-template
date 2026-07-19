// node --test extension/lib.test.js
const test = require("node:test");
const assert = require("node:assert");
const {
  slugify,
  parsePostUrl,
  cleanBodyText,
  postFilename,
  makeMarkdown,
  parseNaverDate,
  naverDateFromHtml,
} = require("./lib.js");

test("slugify: 한글 제목", () => {
  assert.equal(slugify("블로그 유기 안함요", "123"), "블로그-유기-안함요");
});

test("slugify: 특수문자만 → fallback", () => {
  assert.equal(slugify("!!!???", "224331671749"), "224331671749");
});

test("slugify: 40자 절단", () => {
  assert.ok(slugify("가".repeat(100), "x").length <= 40);
});

test("parsePostUrl: 모바일", () => {
  assert.deepEqual(parsePostUrl("https://m.blog.naver.com/jokebear67/224331671749"), {
    blogId: "jokebear67",
    logNo: "224331671749",
  });
});

test("parsePostUrl: PC PostView iframe", () => {
  assert.deepEqual(
    parsePostUrl("https://blog.naver.com/PostView.naver?blogId=jokebear67&logNo=999&redirect=Dlog"),
    { blogId: "jokebear67", logNo: "999" }
  );
});

test("parsePostUrl: 글 아닌 페이지", () => {
  assert.equal(parsePostUrl("https://m.blog.naver.com/jokebear67?tab=1"), null);
});

test("cleanBodyText: 공백/빈줄 정리", () => {
  assert.equal(cleanBodyText("첫  줄\n\n\n둘째\t줄  "), "첫 줄\n\n둘째 줄");
});

test("postFilename", () => {
  assert.equal(postFilename("2026-07-16", "테스트 글", "999"), "2026-07-16-테스트-글.md");
});

test("makeMarkdown: frontmatter + 따옴표 치환", () => {
  const md = makeMarkdown({ title: '제목 "따옴표"', date: "2026-07-16", url: "https://x/1", body: "본문" });
  assert.ok(md.startsWith("---\n"));
  assert.ok(md.includes("title: \"제목 '따옴표'\""));
  assert.ok(md.includes("date: 2026-07-16"));
  assert.ok(md.trimEnd().endsWith("본문"));
});

test("parseNaverDate: 네이버 표기", () => {
  assert.equal(parseNaverDate("2026. 7. 5. 23:06", "2026-07-16"), "2026-07-05");
});

test("parseNaverDate: 상대시간 → fallback", () => {
  assert.equal(parseNaverDate("3시간 전", "2026-07-16"), "2026-07-16");
});

test("naverDateFromHtml: addDate epoch ms (KST)", () => {
  // 1782791426162 = 2026-06-30 KST
  assert.equal(naverDateFromHtml('foo addDate="1782791426162" bar'), "2026-06-30");
});

test("naverDateFromHtml: 화면 표기 폴백", () => {
  assert.equal(naverDateFromHtml("<span>2026. 6. 30.</span>"), "2026-06-30");
});

test("naverDateFromHtml: 없으면 null", () => {
  assert.equal(naverDateFromHtml("<html>no date</html>"), null);
});
