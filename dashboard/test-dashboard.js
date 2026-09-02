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
const { start, trainingBatch, brandDiscoveryCommand, listenFailureMessage } = require("./server");

const repoRoot = path.join(__dirname, "..");
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), "shopbot-dashboard-"));
const suggestionsFile = path.join(tempRoot, "suggestions.json");
const trainingBatchFile = path.join(tempRoot, "training-batch.json");
const votesFile = path.join(tempRoot, "votes.json");
const outcomesFile = path.join(tempRoot, "outcomes.json");
const brandCandidatesFile = path.join(tempRoot, "brand-candidates.json");
const brandDecisionsFile = path.join(tempRoot, "brand-decisions.json");
const crawlerReportFile = path.join(tempRoot, "crawler-last-run.json");
const ingestionCandidatesFile = path.join(tempRoot, "ingestion-candidates.json");
const suggestion = {
  id: "test-suggestion",
  title: "Test jacket",
  url: "https://example.com/jacket",
  modes: ["classic-casual"],
  category: "jackets",
  verification: { status: "verified", checkedAt: "2026-08-05T00:00:00Z", stock: "in-stock" },
};
const brandCandidate = {
  id: "brand-new-label",
  brand: "New Label",
  reason: "Found through a trusted retailer.",
  representativeProducts: [],
};

function writeFixture() {
  fs.writeFileSync(suggestionsFile, JSON.stringify({ suggestions: [suggestion] }), "utf8");
  fs.writeFileSync(trainingBatchFile, JSON.stringify({ version: 1, title: "Test training", description: "Balanced", quotas: { jackets: 1 }, itemIds: ["test-suggestion"] }), "utf8");
  fs.writeFileSync(votesFile, "{}\n", "utf8");
  fs.writeFileSync(outcomesFile, "{}\n", "utf8");
  fs.writeFileSync(brandCandidatesFile, JSON.stringify({ candidates: [brandCandidate] }), "utf8");
  fs.writeFileSync(brandDecisionsFile, "{}\n", "utf8");
  fs.writeFileSync(crawlerReportFile, JSON.stringify({ sources: [{ sourceId: "zara-us", activeBefore: 17, blocked: false, policy: { initialTarget: 24 } }] }), "utf8");
  fs.writeFileSync(ingestionCandidatesFile, JSON.stringify({ generatedAt: "2026-09-01T00:00:00Z", candidates: [{ id: "lead-1" }, { id: "lead-2" }], sources: [{ sourceId: "levis", ok: true }] }), "utf8");
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

async function postOutcome(port, id, outcome, extraHeaders) {
  return request(port, "POST", "/api/outcome", { id, outcome }, { "Content-Type": "application/json", ...(extraHeaders || {}) });
}

async function postBrandDecision(port, id, decision, extraHeaders) {
  return request(port, "POST", "/api/brand-decision", { id, decision }, { "Content-Type": "application/json", ...(extraHeaders || {}) });
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
    STATE = { suggestions: ${JSON.stringify(items)}, votes: { "old-verified": { vote: 2 } }, outcomes: {}, voteScale: [], outcomeOptions: [] };
    const testItems = STATE.suggestions;
    FILTERS = { ...FILTER_DEFAULTS };
    const defaultVoteFilter = FILTERS.vote;
    const reviewQueueIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS = { ...FILTER_DEFAULTS, status: "expired", vote: "any" };
    const expiredIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS.status = "needs-verification";
    const verificationQueueIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS.status = "verified";
    const verifiedIds = filteredSuggestions().map((item) => item.id).sort();
    FILTERS.status = "lead";
    const leadIds = filteredSuggestions().map((item) => item.id).sort();
    globalThis.results = {
      statuses: testItems.map((item) => effectiveStatus(item, ${now})),
      defaultVoteFilter,
      reviewQueueIds,
      expiredIds,
      verificationQueueIds,
      verifiedIds,
      leadIds,
      oldCard: suggestionCard(testItems[0]),
      missingCard: suggestionCard(testItems[2])
    };
  `, context);
  assert.deepStrictEqual(Array.from(context.results.statuses), ["expired", "verified", "lead", "lead"]);
  assert.strictEqual(context.results.defaultVoteFilter, "unvoted");
  assert.deepStrictEqual(Array.from(context.results.reviewQueueIds), ["fresh-lead", "fresh-verified", "missing-lead"]);
  assert.deepStrictEqual(Array.from(context.results.expiredIds), ["old-verified"]);
  assert.deepStrictEqual(Array.from(context.results.verificationQueueIds), ["old-verified"]);
  assert.deepStrictEqual(Array.from(context.results.verifiedIds), ["fresh-verified"]);
  assert.deepStrictEqual(Array.from(context.results.leadIds), ["fresh-lead", "missing-lead"]);
  assert.ok(context.results.oldCard.includes('status-chip expired'), "old verified chip should render expired");
  assert.ok(context.results.oldCard.includes('verification expired'), "old verified details should render expired");
  assert.ok(context.results.missingCard.includes('status-chip lead'), "lead without checkedAt should remain a lead");
  assert.ok(context.results.missingCard.includes('discovery lead'), "lead details should not claim expired verification");
}

function assertCatalogSummary() {
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  const initAt = scriptMatch[1].lastIndexOf("\ndocument.querySelectorAll('[role=\"tab\"]')");
  const clientCore = scriptMatch[1].slice(0, initAt);
  const context = {};
  vm.runInNewContext(clientCore + `
    globalThis.results = catalogSummary({
      suggestions: [
        { id: "zara-1", provenance: { sourceId: "zara-us" }, verification: { stock: "in-stock" } },
        { id: "ae-1", provenance: { sourceId: "ae" }, verification: { stock: "in-stock" } },
        { id: "ae-rejected", provenance: { sourceId: "ae" }, verification: { stock: "in-stock" } },
        { id: "other", provenance: { sourceId: "other" }, verification: { stock: "in-stock" } }
      ],
      votes: { "ae-rejected": { vote: -2 } },
      crawlerReport: { sources: [
        { sourceId: "zara-us", policy: { initialTarget: 24 }, blocked: false, backpressure: true },
        { sourceId: "ae", policy: { initialTarget: 12 }, blocked: false, backpressure: false }
      ] }
    });
  `, context);
  assert.strictEqual(context.results.active, 2);
  assert.strictEqual(context.results.target, 36);
  assert.strictEqual(context.results.status, "waiting for votes");
}

function assertPersonalizedRanking() {
  const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  const initAt = scriptMatch[1].lastIndexOf("\ndocument.querySelectorAll('[role=\"tab\"]')");
  const clientCore = scriptMatch[1].slice(0, initAt);
  const training = Array.from({ length: 15 }, (_, index) => ({
    id: "train-" + index,
    title: "Training " + index,
    brand: index < 8 ? "Heritage" : "Tech",
    category: "outerwear",
    modes: [index < 8 ? "classic-casual" : "athletic-tech"],
    addedAt: "2026-01-01T00:00:00Z",
    verification: { status: "lead" },
  }));
  const candidates = [
    { id: "candidate-liked", title: "Liked candidate", brand: "Heritage", category: "outerwear", modes: ["classic-casual"], addedAt: "2026-01-01T00:00:00Z", verification: { status: "lead" } },
    { id: "candidate-disliked", title: "Disliked candidate", brand: "Tech", category: "outerwear", modes: ["athletic-tech"], addedAt: "2026-01-02T00:00:00Z", verification: { status: "lead" } },
  ];
  const outcomeOnly = { id: "outcome-only", title: "Owned item", brand: "Outcome", category: "accessories", modes: ["minimal-clean"], addedAt: "2026-01-03T00:00:00Z", verification: { status: "lead" } };
  const votes = Object.fromEntries(training.map((item, index) => [item.id, { vote: index < 8 ? 1 : -1 }]));
  const context = {};
  vm.runInNewContext(clientCore + `
    STATE = { suggestions: ${JSON.stringify([...training, ...candidates, outcomeOnly])}, votes: ${JSON.stringify(votes)}, outcomes: { "train-0": { outcome: "repeat-wear" }, "outcome-only": { outcome: "repeat-wear" } }, voteScale: [], outcomeOptions: [] };
    FILTERS = { ...FILTER_DEFAULTS };
    const model = personalizationModel(STATE.suggestions);
    globalThis.results = { ready: model.ready, voteCount: model.voteCount, outcomeSignal: model.signals["brand:outcome"].total, ranked: filteredSuggestions().map((item) => item.id) };
  `, context);
  assert.strictEqual(context.results.ready, true);
  assert.strictEqual(context.results.voteCount, 15);
  assert.strictEqual(context.results.outcomeSignal, 4);
  assert.deepStrictEqual(Array.from(context.results.ranked), ["candidate-liked", "candidate-disliked"]);
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

function assertTrainingBatch() {
  const result = trainingBatch({
    version: 2,
    title: "Balanced",
    quotas: { pants: 1, broken: 0 },
    itemIds: ["known", "missing", "known", 42],
  }, [{ id: "known", category: "pants" }]);
  assert.strictEqual(result.version, 2);
  assert.deepStrictEqual(result.quotas, { pants: 1 });
  assert.deepStrictEqual(result.items.map((item) => item.id), ["known"]);
  assert.deepStrictEqual(result.missingIds, ["missing"]);
}

function assertBrandDiscoveryCommand() {
  assert.deepStrictEqual(brandDiscoveryCommand("/repo", "win32"), { command: "py", args: ["-3", path.join("/repo", "engine", "discover-brands.py")] });
  assert.deepStrictEqual(brandDiscoveryCommand("/repo", "darwin"), { command: "python3", args: [path.join("/repo", "engine", "discover-brands.py")] });
}

async function main() {
  assertEffectiveVerificationStatus();
  assertCatalogSummary();
  assertPersonalizedRanking();
  assertTrainingBatch();
  assertListenDiagnostics();
  assertBrandDiscoveryCommand();
  writeFixture();
  const server = await start({
    port: 0,
    silent: true,
    brandDiscovery: false,
    root: repoRoot,
    dataPaths: {
      suggestions: suggestionsFile,
      trainingBatch: trainingBatchFile,
      votes: votesFile,
      outcomes: outcomesFile,
      brandCandidates: brandCandidatesFile,
      brandDecisions: brandDecisionsFile,
      crawlerReport: crawlerReportFile,
      ingestionCandidates: ingestionCandidatesFile,
      pinterest: path.join(tempRoot, "missing-pinterest.json"),
      watches: path.join(tempRoot, "missing-watches.json"),
      corpus: path.join(repoRoot, "taste", "corpus"),
      productImages: path.join(repoRoot, "data", "images"),
    },
  });
  const port = server.address().port;
  try {
    await assert.rejects(start({ port, host: "127.0.0.1", silent: true, brandDiscovery: false }), (error) =>
      error.code === "EADDRINUSE" && error.dashboardHost === "127.0.0.1" && error.dashboardPort === port
    );
    const initial = await getState(port);
    assert.deepStrictEqual(initial.voteScale.map((entry) => entry.value), [-2, -1, 0, 1, 2]);
    assert.deepStrictEqual(initial.outcomeOptions.map((entry) => entry.value), ["bought", "kept", "returned", "repeat-wear"]);
    assert.deepStrictEqual(initial.outcomes, {});
    assert.deepStrictEqual(initial.brandDecisions, {});
    assert.strictEqual(initial.brandCandidates[0].brand, "New Label");
    assert.strictEqual(initial.crawlerReport.sources[0].activeBefore, 17);
    assert.deepStrictEqual(initial.ingestion, { generatedAt: "2026-09-01T00:00:00Z", candidateCount: 2, sources: [{ sourceId: "levis", ok: true }] });
    assert.deepStrictEqual(initial.brandDecisionOptions.map((entry) => entry.value), ["follow", "occasional", "reject", "too-expensive"]);
    const corpusCount = fs.readdirSync(path.join(repoRoot, "taste", "corpus")).filter((f) => /^clothes-\d+\.jpg$/i.test(f)).length;
    assert.ok(corpusCount > 0, "corpus fixture should not be empty");
    assert.strictEqual(initial.tabs.taste.count, corpusCount);
    assert.strictEqual(initial.tabs.training.count, 1);
    assert.strictEqual(initial.trainingBatch.title, "Test training");
    assert.deepStrictEqual(initial.trainingBatch.items.map((item) => item.id), ["test-suggestion"]);
    assert.strictEqual(initial.tabs.suggestions.count, 1);
    assert.strictEqual(initial.tabs.brands.count, 1);

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

    for (const outcome of ["bought", "kept", "returned", "repeat-wear"]) {
      response = await postOutcome(port, "test-suggestion", outcome);
      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.json.outcomes["test-suggestion"].outcome, outcome);
      assert.strictEqual((await getState(port)).outcomes["test-suggestion"].outcome, outcome);
    }
    response = await postOutcome(port, "test-suggestion", "none");
    assert.strictEqual(response.status, 200);
    assert.ok(!response.json.outcomes["test-suggestion"], "none should clear the purchase outcome");
    const outcomeBefore = fs.readFileSync(outcomesFile, "utf8");
    for (const [body, message] of [
      [{ id: "test-suggestion", outcome: "wanted" }, "unknown outcome"],
      [{ id: "clothes-01", outcome: "bought" }, "non-suggestion id"],
      [{ id: "../test-suggestion", outcome: "kept" }, "traversal id"],
      [{ outcome: "kept" }, "missing id"],
      [{ id: "test-suggestion" }, "missing outcome"],
    ]) {
      response = await request(port, "POST", "/api/outcome", body, { "Content-Type": "application/json" });
      assert.strictEqual(response.status, 400, message + " should reject");
      assert.strictEqual(fs.readFileSync(outcomesFile, "utf8"), outcomeBefore, message + " changed outcomes");
    }
    response = await request(port, "GET", "/api/outcome");
    assert.strictEqual(response.status, 405);
    assert.strictEqual(response.headers.allow, "POST");
    response = await postOutcome(port, "test-suggestion", "kept", { "Content-Type": "text/plain" });
    assert.strictEqual(response.status, 415);
    assert.strictEqual(fs.readFileSync(outcomesFile, "utf8"), outcomeBefore, "wrong content type changed outcomes");
    response = await request(port, "POST", "/api/outcome", "x".repeat(9000), { "Content-Type": "application/json" });
    assert.strictEqual(response.status, 413);
    assert.strictEqual(fs.readFileSync(outcomesFile, "utf8"), outcomeBefore, "oversized body changed outcomes");
    await postOutcome(port, "test-suggestion", "kept");
    await postOutcome(port, "test-suggestion", "kept");
    assert.deepStrictEqual(Object.keys(JSON.parse(fs.readFileSync(outcomesFile, "utf8"))), ["test-suggestion"], "retries should remain idempotent");
    await postOutcome(port, "test-suggestion", "none");

    for (const decision of ["follow", "occasional", "reject", "too-expensive"]) {
      response = await postBrandDecision(port, "brand-new-label", decision);
      assert.strictEqual(response.status, 200);
      assert.strictEqual(response.json.brandDecisions["brand-new-label"].decision, decision);
      assert.strictEqual((await getState(port)).brandDecisions["brand-new-label"].decision, decision);
    }
    response = await postBrandDecision(port, "brand-new-label", "none");
    assert.strictEqual(response.status, 200);
    assert.ok(!response.json.brandDecisions["brand-new-label"]);
    const brandDecisionBefore = fs.readFileSync(brandDecisionsFile, "utf8");
    for (const [body, message] of [
      [{ id: "brand-new-label", decision: "love" }, "unknown brand decision"],
      [{ id: "brand-missing", decision: "follow" }, "unknown brand id"],
      [{ id: "../brand-new-label", decision: "follow" }, "brand traversal id"],
      [{ decision: "follow" }, "missing brand id"],
      [{ id: "brand-new-label" }, "missing brand decision"],
    ]) {
      response = await request(port, "POST", "/api/brand-decision", body, { "Content-Type": "application/json" });
      assert.strictEqual(response.status, 400, message + " should reject");
      assert.strictEqual(fs.readFileSync(brandDecisionsFile, "utf8"), brandDecisionBefore, message + " changed decisions");
    }
    response = await request(port, "GET", "/api/brand-decision");
    assert.strictEqual(response.status, 405);
    assert.strictEqual(response.headers.allow, "POST");
    response = await postBrandDecision(port, "brand-new-label", "follow", { "Content-Type": "text/plain" });
    assert.strictEqual(response.status, 415);
    response = await request(port, "POST", "/api/brand-decision", "x".repeat(9000), { "Content-Type": "application/json" });
    assert.strictEqual(response.status, 413);
    await postBrandDecision(port, "brand-new-label", "follow");
    await postBrandDecision(port, "brand-new-label", "follow");
    assert.deepStrictEqual(Object.keys(JSON.parse(fs.readFileSync(brandDecisionsFile, "utf8"))), ["brand-new-label"], "brand decision retries should remain idempotent");
    await postBrandDecision(port, "brand-new-label", "none");
    fs.writeFileSync(brandDecisionsFile, JSON.stringify({ "brand-evicted": { decision: "follow", at: "old" } }), "utf8");
    response = await postBrandDecision(port, "brand-new-label", "occasional");
    assert.strictEqual(response.status, 200);
    assert.strictEqual(response.json.brandDecisions["brand-evicted"].decision, "follow", "updating a retained brand must preserve an evicted brand decision");
    assert.strictEqual(JSON.parse(fs.readFileSync(brandDecisionsFile, "utf8"))["brand-evicted"].decision, "follow");
    fs.writeFileSync(brandDecisionsFile, "{}\n", "utf8");
    const outcomeBurst = Array.from({ length: 20 }, (_, index) => postOutcome(port, "test-suggestion", ["bought", "kept", "returned", "repeat-wear"][index % 4]));
    await Promise.all(outcomeBurst);
    const burstOutcomes = JSON.parse(fs.readFileSync(outcomesFile, "utf8"));
    assert.strictEqual(burstOutcomes["test-suggestion"].outcome, "repeat-wear", "serialized outcome writes should preserve the final update");
    await postOutcome(port, "test-suggestion", "none");

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
    fs.writeFileSync(outcomesFile, JSON.stringify({ "test-suggestion": { outcome: "invented" } }), "utf8");
    fs.writeFileSync(suggestionsFile, "{", "utf8");
    const corrupt = await getState(port);
    assert.deepStrictEqual(corrupt.votes, {});
    assert.deepStrictEqual(corrupt.outcomes, {});
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
