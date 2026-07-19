// 글 페이지에서 본문을 추출해 background로 넘긴다.
// 판단(공개/비공개, 커밋 여부)은 전부 background 몫 — 여기는 추출만.
(function () {
  const post = parsePostUrl(location.href);
  if (!post) return;

  function extract() {
    const container = BODY_SELECTORS.map((s) => document.querySelector(s)).find(Boolean);
    if (!container) return null;
    const body = cleanBodyText(container.innerText);
    if (!body) return null;
    const title =
      document.querySelector(".se-title-text")?.innerText.trim() ||
      document.querySelector(".pcol1")?.innerText.trim() ||
      document.title.replace(/ : 네이버 블로그.*$/, "").trim();
    const dateText =
      document.querySelector(".blog_date, .se_publishDate, .date")?.innerText || "";
    // addDate 속성(epoch ms)은 초기 HTML에 있어 렌더링 타이밍과 무관하게 정확
    const addDateMs =
      document.querySelector("[addDate]")?.getAttribute("addDate") || "";
    return { ...post, title, body, dateText, addDateMs, url: location.href };
  }

  // 에디터 렌더링이 늦을 수 있어 잠깐 재시도
  let tries = 0;
  const timer = setInterval(() => {
    const data = extract();
    tries += 1;
    if (data) {
      clearInterval(timer);
      chrome.runtime.sendMessage({ type: "post-viewed", data });
    } else if (tries > 10) {
      clearInterval(timer);
    }
  }, 500);
})();
