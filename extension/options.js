const FIELDS = ["token", "owner", "repo", "myBlogId"];

chrome.storage.sync.get(Object.fromEntries(FIELDS.map((f) => [f, ""]))).then((cfg) => {
  for (const f of FIELDS) document.getElementById(f).value = cfg[f];
});

document.getElementById("backfill").addEventListener("click", async () => {
  const el = document.getElementById("backfillStatus");
  let total = { fixed: 0, skipped: 0, failed: 0 };
  // 워커 5분 제한 때문에 배치로 끊어 돌므로 done까지 반복 호출
  for (let round = 1; round <= 20; round++) {
    el.textContent = ` ${round}차 진행 중... (누적 교정 ${total.fixed})`;
    const r = await new Promise((res) =>
      chrome.runtime.sendMessage({ type: "backfill-dates" }, res)
    );
    if (!r || r.error) {
      el.textContent = ` 실패: ${r?.error || "응답 없음"} (누적 교정 ${total.fixed})`;
      return;
    }
    total.fixed += r.fixed;
    total.skipped = r.skipped;
    total.failed += r.failed;
    if (r.done) break;
  }
  el.textContent = ` 완료 — 교정 ${total.fixed}, 이미 정상 ${total.skipped}, 실패 ${total.failed}`;
});

document.getElementById("save").addEventListener("click", async () => {
  const cfg = Object.fromEntries(FIELDS.map((f) => [f, document.getElementById(f).value.trim()]));
  await chrome.storage.sync.set(cfg);
  document.getElementById("status").textContent = "저장됨";
  setTimeout(() => (document.getElementById("status").textContent = ""), 2000);
});
