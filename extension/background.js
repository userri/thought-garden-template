importScripts("lib.js");

const API = "https://api.github.com";
// 중복 커밋 방지는 commitFile의 기존 내용 비교로 충분 — 메모리 캐시를 두면
// 레포에서 파일을 지운 뒤 재열람해도 커밋이 안 되는 문제가 생긴다.

async function getConfig() {
  return chrome.storage.sync.get({ token: "", owner: "", repo: "", myBlogId: "" });
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon.png",
    title: `thought-garden: ${title}`,
    message,
  });
}

// 쿠키 없이 같은 글을 요청해 본문이 보이면 공개 글.
async function isPublicPost(blogId, logNo) {
  const resp = await fetch(`https://m.blog.naver.com/${blogId}/${logNo}`, {
    credentials: "omit",
  });
  if (!resp.ok) return false;
  const html = await resp.text();
  return BODY_SELECTORS.some((sel) => {
    const cls = sel.replace(/^div[.#]/, "");
    return html.includes(`class="${cls}`) || html.includes(`id="${cls}`);
  });
}

async function commitFile(cfg, path, content, message) {
  const url = `${API}/repos/${cfg.owner}/${cfg.repo}/contents/${encodeURIComponent(path)}`;
  const headers = {
    Authorization: `Bearer ${cfg.token}`,
    Accept: "application/vnd.github+json",
  };
  const existing = await fetch(url, { headers });
  const body = { message, content: toBase64Utf8(content) };
  if (existing.ok) {
    const prev = await existing.json();
    const prevContent = (prev.content || "").replace(/\n/g, "");
    if (prevContent === body.content) return "unchanged";
    body.sha = prev.sha;
  }
  const put = await fetch(url, { method: "PUT", headers, body: JSON.stringify(body) });
  if (!put.ok) throw new Error(`GitHub ${put.status}: ${(await put.text()).slice(0, 200)}`);
  return existing.ok ? "updated" : "created";
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "post-viewed") {
    handlePost(msg.data).catch((e) => notify("커밋 실패", String(e)));
    sendResponse(true);
  } else if (msg.type === "backfill-dates") {
    backfillDates()
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ error: String(e) }));
    return true; // async sendResponse
  }
});

// private-posts/ 전체의 날짜를 네이버 원본(addDate)으로 교정한다.
// 로그인된 브라우저에서 돌므로 비공개 글 날짜도 조회 가능. LLM 호출 없음.
// MV3 워커는 5분이면 강제 종료되므로 한 호출당 교정 60편에서 끊고,
// options 페이지가 done=true 까지 반복 호출한다.
const BACKFILL_BATCH = 60;

async function backfillDates() {
  const cfg = await getConfig();
  const headers = {
    Authorization: `Bearer ${cfg.token}`,
    Accept: "application/vnd.github+json",
  };
  const listResp = await fetch(
    `${API}/repos/${cfg.owner}/${cfg.repo}/contents/private-posts`,
    { headers }
  );
  if (!listResp.ok) throw new Error(`목록 조회 실패: ${listResp.status}`);
  const files = (await listResp.json()).filter((f) => f.name.endsWith(".md"));
  let fixed = 0, skipped = 0, failed = 0, done = true;
  for (const item of files) {
    if (fixed >= BACKFILL_BATCH) { done = false; break; }
    try {
      const file = await (await fetch(item.url, { headers })).json();
      const md = fromBase64Utf8(file.content);
      const logNo = md.match(/^url: .*\/(\d+)\s*$/m)?.[1];
      if (!logNo) { failed++; continue; }
      const page = await fetch(`https://m.blog.naver.com/${cfg.myBlogId}/${logNo}`);
      const trueDate = naverDateFromHtml(await page.text());
      if (!trueDate) { failed++; continue; }
      if (item.name.startsWith(trueDate)) { skipped++; continue; }
      const newName = trueDate + item.name.slice(10); // YYYY-MM-DD 프리픽스 교체
      const newMd = md.replace(/^date: .*$/m, `date: ${trueDate}`);
      await commitFile(cfg, `private-posts/${newName}`, newMd, `fix-date: ${newName}`);
      await fetch(`${API}/repos/${cfg.owner}/${cfg.repo}/contents/${encodeURIComponent(`private-posts/${item.name}`)}`, {
        method: "DELETE",
        headers,
        body: JSON.stringify({ message: `fix-date: remove ${item.name}`, sha: file.sha }),
      });
      fixed++;
    } catch (e) {
      failed++;
    }
  }
  const result = { fixed, skipped, failed, done, total: files.length };
  if (done) notify("날짜 백필 완료", `교정 ${fixed} / 이미 정상 ${skipped} / 실패 ${failed}`);
  return result;
}

async function handlePost(data) {
  const cfg = await getConfig();
  if (!cfg.token || !cfg.owner || !cfg.repo || !cfg.myBlogId) return; // 미설정 시 침묵
  if (data.blogId !== cfg.myBlogId) return; // 남의 블로그는 무시

  if (await isPublicPost(data.blogId, data.logNo)) return; // 공개 글은 v1(RSS)이 담당

  const today = new Date().toISOString().slice(0, 10);
  const date = data.addDateMs
    ? naverDateFromHtml(`addDate="${data.addDateMs}"`)
    : parseNaverDate(data.dateText, today);
  const filename = postFilename(date, data.title, data.logNo);
  const md = makeMarkdown({
    title: data.title,
    date,
    url: `https://blog.naver.com/${data.blogId}/${data.logNo}`,
    body: data.body,
  });
  const result = await commitFile(cfg, `private-posts/${filename}`, md, `harvest(private): ${data.title}`);
  if (result !== "unchanged") notify("비공개 글 수확", `${filename} (${result})`);
}
