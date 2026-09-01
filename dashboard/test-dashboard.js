// Every assert goes through this proxy so the summary line reports the real number of
// checks executed. A hardcoded "1 passed" hides a suite that silently stopped asserting.
let assertions = 0;
const assert = new Proxy(require("assert"), {
  get(target, prop) {
    const value = target[prop];
    if (typeof value !== "function") return value;
    return (...args) => { assertions += 1; return value(...args); };
  },
});
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const vm = require("vm");
const { start, listenFailureMessage } = require("./server");

const repoRoot = path.join(__dirname, "..");
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "shopbot-dashboard-"));
const suggestionsFile = path.join(tempRoot, "suggestions.json");
const votesFile = path.join(tempRoot, "votes.json");
const suggestion = {
  id: "test-suggestion",
  title: "Test jacket",
  url: "https://example.com/jacket",
  modes: ["classic-casual"],
  category: "jackets",
  verification: { status: "verified", checkedAt: "2026-08-05T00:00:00Z", stock: "in-stock" },
};

function writeFixture() {
  fs.writeFileSync(suggestionsFile, JSON.stringify({ suggestions: [suggestion] }), "utf8");
  fs.writeFileSync(votesFile, "{}\n", "utf8");
}

function request(port, method, route, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? "" : typeof body === "string" ? body : JSON.stringify(body);
    const req = http.request({
      host: "127.0.0.1", port, method, path: route,
      headers: { ...(body === undefined ? {} : { "Content-Length": Buffer.byteLength(payload) }), ...headers },
    }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const raw = Buffer.concat(chunks).toString("utf8");
        let json = null;
        try { json = JSON.parse(raw); } catch (_) {}
        resolve({ status: res.statusCode, headers: res.headers, raw, json });
      });
    });
    req.setTimeout(3000, () => req.destroy(new Error("request timeout")));
    req.on("error", reject);
    if (body !== undefined) req.write(payload);
    req.end();
  });
}

async function getState(port) {
  const response = await request(port, "GET", "/api/state");
  assert.strictEqual(response.status, 200);
  assert.strictEqual(response.headers["cache-control"], "no-store");
  return response.json;
}

async function postVote(port, id, vote, extraHeaders) {
  return request(port, "POST", "/api/vote", { id, vote }, { "Content-Type": "application/json", ...(extraHeaders || {}) });
}

function assertRejectedWithoutWrite(port, before, response, message) {
  assert.ok(response.status >= 400, message + " should reject");
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(votesFile, "utf8")), JSON.parse(before), message + " changed votes");
}

function assertEffectiveVerificationStatus() {
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  assert.ok(scriptMatch, "dashboard client script should exist");
  const initMarker = "\ndocument.querySelectorAll('[role=\"tab\"]').forEach((tab) => { tab.addEventListener";
  const initAt = scriptMatch[1].lastIndexOf(initMarker);
  assert.ok(initAt > 0, "dashboard client initialization should exist");
  const clientCore = scriptMatch[1].slice(0, initAt);
  const now = Date.now();
  const items = [
    { id: "old-verified", title: "Old verified", verification: { status: "verified", checkedAt: new Date(now - 8 * 86400000).toISOString() } },
    { id: "fresh-verified", title: "Fresh verified", verification: { status: "verified", checkedAt: new Date(now - 6 * 86400000).toISOString() } },
    { id: "missing-lead", title: "Missing time", verification: { status: "lead" } },
    { id: "fresh-lead", title: "Fresh lead", verification: { status: "lead", checkedAt: new Date(now - 6 * 86400000).toISOString() } },
  ];
  const context = {};
  vm.runInNewContext(clientCore + `
    STATE = { suggestions: ${JSON.stringify(items)}, votes: {}, voteScale: [] };
    const testItems = STATE.suggestions;
    FILTERS = { ...FILTER_DEFAULTS, status: "stale" };
    const staleIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS.status = "verified";
    const verifiedIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS.status = "lead";
    const leadIds = filteredSuggestions().map((item) => item.id).sort();
    globalThis.results = {
      statuses: testItems.map((item) => effectiveStatus(item, ${now})),
      staleIds,
      verifiedIds,
      leadIds,
      oldCard: suggestionCard(testItems[0]),
      missingCard: suggestionCard(testItems[2])
    };
  `, context);
  assert.deepStrictEqual(Array.from(context.results.statuses), ["stale", "verified", "stale", "lead"]);
  assert.deepStrictEqual(Array.from(context.results.staleIds), ["missing-lead", "old-verified"]);
  assert.deepStrictEqual(Array.from(context.results.verifiedIds), ["fresh-verified"]);
  assert.deepStrictEqual(Array.from(context.results.leadIds), ["fresh-lead"]);
  assert.ok(context.results.oldCard.includes('status-chip stale'), "old verified chip should render stale");
  assert.ok(context.results.oldCard.includes('verification stale'), "old verified details should render stale");
  assert.ok(context.results.missingCard.includes('status-chip stale'), "missing checkedAt chip should render stale");
  assert.ok(context.results.missingCard.includes('verification stale'), "missing checkedAt details should render stale");
}

function assertListenDiagnostics() {
  let lookupTarget = null;
  const message = listenFailureMessage({ code: "EADDRINUSE" }, "127.0.0.1", 7877, (host, port) => {
    lookupTarget = { host, port };
    return "node.exe (PID 4242)";
  });
  assert.deepStrictEqual(lookupTarget, { host: "127.0.0.1", port: 7877 });
  assert.ok(message.includes("host=127.0.0.1 port=7877 code=EADDRINUSE"));
  assert.ok(message.includes("owner=node.exe (PID 4242)"));
}

async function main() {
  assertEffectiveVerificationStatus();
  assertListenDiagnostics();
  writeFixture();
  const server = await start({
    port: 0,
    silent: true,
    root: repoRoot,
    dataPaths: {
      suggestions: suggestionsFile,
      votes: votesFile,
      pinterest: path.join(tempRoot, "missing-pinterest.json"),
      watches: path.join(tempRoot, "missing-watches.json"),
      corpus: path.join(repoRoot, "taste", "corpus"),
      productImages: path.join(repoRoot, "data", "images"),
    },
  });
  const port = server.address().port;
  try {
    await assert.rejects(start({ port, host: "127.0.0.1", silent: true }), (error) =>
      error.code === "EADDRINUSE" && error.dashboardHost === "127.0.0.1" && error.dashboardPort === port
    );
    const initial = await getState(port);
    assert.deepStrictEqual(initial.voteScale.map((entry) => entry.value), [-2, -1, 0, 1, 2]);
    const corpusCount = fs.readdirSync(path.join(repoRoot, "taste", "corpus")).filter((f) => /^clothes-\d+\.jpg$/i.test(f)).length;
    assert.ok(corpusCount > 0, "corpus fixture should not be empty");
    assert.strictEqual(initial.tabs.taste.count, corpusCount);
    assert.strictEqual(initial.tabs.suggestions.count, 1);

    for (const level of [-2, -1, 1, 2]) {
      const response = await postVote(port, "clothes-01", level);
      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.json.votes["clothes-01"].vote, level);
      const state = await getState(port);
      assert.strictEqual(state.votes["clothes-01"].vote, level);
    }
    let response = await postVote(port, "clothes-01", 0);
    assert.strictEqual(response.status, 200);
    assert.ok(!response.json.votes["clothes-01"], "vote 0 should delete the key");
    response = await postVote(port, "clothes-01", 1);
    assert.strictEqual(response.status, 200);
    const current = await getState(port);
    const toggled = current.votes["clothes-01"].vote === 1 ? 0 : 1;
    response = await postVote(port, "clothes-01", toggled);
    assert.strictEqual(response.status, 200);
    assert.ok(!response.json.votes["clothes-01"], "reselecting the active level should clear it");

    await postVote(port, "clothes-02", 2);
    const before = fs.readFileSync(votesFile, "utf8");
    const invalid = [
      [{ id: "clothes-02", vote: 1.5 }, "non-integer vote"],
      [{ id: "clothes-02", vote: 3 }, "vote 3"],
      [{ id: "clothes-02", vote: -3 }, "vote -3"],
      [{ id: "clothes-02", vote: "1" }, "string vote"],
      [{ id: "clothes-02" }, "missing vote"],
      [{ vote: 1 }, "missing id"],
      [{ id: "not-known", vote: 1 }, "unknown id"],
      [{ id: "../clothes-02", vote: 1 }, "traversal id"],
      [{ id: "CLOTHES-02", vote: 1 }, "uppercase id"],
      [{ id: "a".repeat(65), vote: 1 }, "over-long id"],
    ];
    for (const [body, message] of invalid) {
      response = await request(port, "POST", "/api/vote", body, { "Content-Type": "application/json" });
      assertRejectedWithoutWrite(port, before, response, message);
      assert.strictEqual(response.json.ok, false, message + " should return ok false");
    }
    response = await request(port, "GET", "/api/vote");
    assert.strictEqual(response.status, 405);
    assert.strictEqual(response.headers.allow, "POST");
    assertRejectedWithoutWrite(port, before, response, "non-POST");
    response = await postVote(port, "clothes-02", 1, { "Content-Type": "text/plain" });
    assert.strictEqual(response.status, 415);
    assertRejectedWithoutWrite(port, before, response, "wrong content type");
    response = await request(port, "POST", "/api/vote", "x".repeat(9000), { "Content-Type": "application/json" });
    assert.strictEqual(response.status, 413);
    assertRejectedWithoutWrite(port, before, response, "oversized body");

    const burst = Array.from({ length: 30 }, (_, index) => postVote(port, "clothes-" + String(index + 1).padStart(2, "0"), index % 5 - 2));
    await Promise.all(burst);
    const burstFile = fs.readFileSync(votesFile, "utf8");
    const burstVotes = JSON.parse(burstFile);
    assert.strictEqual(Object.keys(burstVotes).length, 24, "zero votes should not be stored");
    assert.strictEqual(burstVotes["clothes-01"].vote, -2);
    assert.strictEqual(burstVotes["clothes-05"].vote, 2);
    assert.strictEqual((await getState(port)).votes["clothes-05"].vote, 2);

    fs.writeFileSync(votesFile, JSON.stringify({ "clothes-01": { vote: 99 }, "clothes-02": { vote: -99 } }), "utf8");
    const clamped = await getState(port);
    assert.strictEqual(clamped.votes["clothes-01"].vote, 2);
    assert.strictEqual(clamped.votes["clothes-02"].vote, -2);
    fs.writeFileSync(votesFile, "not json", "utf8");
    fs.writeFileSync(suggestionsFile, "{", "utf8");
    const corrupt = await getState(port);
    assert.deepStrictEqual(corrupt.votes, {});
    assert.deepStrictEqual(corrupt.suggestions, []);
    writeFixture();

    response = await request(port, "GET", "/taste/corpus/clothes-01.jpg");
    assert.strictEqual(response.status, 200);
    assert.strictEqual(response.headers["content-type"], "image/jpeg");
    for (const route of ["/taste/corpus/not-a-clothes-file.jpg", "/taste/corpus/../server.js", "/taste/corpus/%2e%2e%2fserver.js"]) {
      response = await request(port, "GET", route);
      assert.strictEqual(response.status, 404, route + " should be rejected");
    }

    // Cached product photos: every extension the fetcher can produce must serve with the
    // matching type, and the route must refuse anything that is not one of those files.
    const imageDir = path.join(repoRoot, "data", "images");
    const cached = fs.existsSync(imageDir) ? fs.readdirSync(imageDir).filter((f) => /\.(jpg|png|webp|avif)$/i.test(f)) : [];
    assert.ok(cached.length > 0, "expected cached product images to serve");
    const expectedType = { jpg: "image/jpeg", png: "image/png", webp: "image/webp", avif: "image/avif" };
    for (const file of cached) {
      response = await request(port, "GET", "/product-images/" + file);
      assert.strictEqual(response.status, 200, file + " should serve");
      assert.strictEqual(response.headers["content-type"], expectedType[file.split(".").pop().toLowerCase()]);
    }
    for (const route of ["/product-images/server.js", "/product-images/../server.js", "/product-images/%2e%2e%2fserver.js", "/product-images/missing-item.webp", "/product-images/notes.txt"]) {
      response = await request(port, "GET", route);
      assert.strictEqual(response.status, 404, route + " should be rejected");
    }

    // Every published suggestion should point at an image the route can actually serve.
    const live = JSON.parse(fs.readFileSync(path.join(repoRoot, "data", "suggestions.json"), "utf8")).suggestions;
    for (const item of live) {
      if (!item.imageUrl) continue;
      assert.ok(item.imageUrl.startsWith("/product-images/"), item.id + " image should be locally cached, not hotlinked");
      response = await request(port, "GET", item.imageUrl);
      assert.strictEqual(response.status, 200, item.id + " image should resolve");
    }
    console.log("dashboard tests: " + assertions + " assertions passed, 0 failed");
  } finally {
    await new Promise((resolve) => server.close(resolve));
    fs.rmSync(tempRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error("dashboard tests: " + assertions + " assertions passed, 1 failed");
  console.error(error.stack || error);
  try { fs.rmSync(tempRoot, { recursive: true, force: true }); } catch (_) {}
  process.exitCode = 1;
});
