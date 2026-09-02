// Shopbot dashboard server - zero dependencies, personal-first.
// Serves the dashboard UI and a tiny JSON API; votes persist into taste/votes.json.
//   node dashboard/server.js -> http://localhost:7877
const http = require("http");
const childProcess = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PORT = 7877;
const MAX_BODY_BYTES = 8 * 1024;
const BRAND_DISCOVERY_INTERVAL_MS = 6 * 60 * 60 * 1000;
const ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
// Product photos are cached locally rather than hotlinked: retailer CDNs reject cross-origin
// referers and rotate their URLs, so a stored remote URL would rot into a broken card.
const IMAGE_RE = /^[a-z0-9][a-z0-9-]{0,63}\.(jpg|png|webp|avif)$/i;
const IMAGE_TYPES = { jpg: "image/jpeg", png: "image/png", webp: "image/webp", avif: "image/avif" };
const VOTE_SCALE = [
  { value: -2, label: "Reject", shortLabel: "-2" },
  { value: -1, label: "Not for me", shortLabel: "-1" },
  { value: 0, label: "Clear vote", shortLabel: "0" },
  { value: 1, label: "Shortlist", shortLabel: "+1" },
  { value: 2, label: "Verify and watch", shortLabel: "+2" },
];
const OUTCOME_OPTIONS = [
  { value: "bought", label: "Bought" },
  { value: "kept", label: "Kept" },
  { value: "returned", label: "Returned" },
  { value: "repeat-wear", label: "Wear repeatedly" },
];
const BRAND_DECISION_OPTIONS = [
  { value: "follow", label: "Follow brand" },
  { value: "occasional", label: "Show occasionally" },
  { value: "reject", label: "Not my style" },
  { value: "too-expensive", label: "Too expensive" },
];

const DEFAULT_PATHS = {
  suggestions: path.join(ROOT, "data", "suggestions.json"),
  trainingBatch: path.join(ROOT, "data", "training-batch.json"),
  votes: path.join(ROOT, "taste", "votes.json"),
  outcomes: path.join(ROOT, "taste", "outcomes.json"),
  brandCandidates: path.join(ROOT, "data", "brand-candidates.json"),
  crawlerReport: path.join(ROOT, "data", "crawler-last-run.json"),
  ingestionCandidates: path.join(ROOT, "data", "ingestion-candidates.json"),
  brandDecisions: path.join(ROOT, "taste", "brand-decisions.json"),
  pinterest: path.join(ROOT, "config", "pinterest.json"),
  watches: path.join(ROOT, "config", "watches.json"),
  corpus: path.join(ROOT, "taste", "corpus"),
  productImages: path.join(ROOT, "data", "images"),
};

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function cleanText(value) {
  return String(value || "").replace(/[\u0080-\uFFFF]/g, "");
}

function listeningProcess(host, port) {
  if (process.platform !== "win32") return null;
  const command = [
    "$targetHost = $env:SHOPBOT_LISTEN_HOST",
    "$targetPort = [int]$env:SHOPBOT_LISTEN_PORT",
    "$connection = Get-NetTCPConnection -State Listen -LocalAddress $targetHost -LocalPort $targetPort -ErrorAction SilentlyContinue | Select-Object -First 1",
    "if ($null -eq $connection) { exit 0 }",
    "$owner = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue",
    "if ($null -eq $owner) { Write-Output ('PID {0}' -f $connection.OwningProcess) } else { Write-Output ('{0}.exe (PID {1})' -f $owner.ProcessName, $connection.OwningProcess) }",
  ].join("; ");
  try {
    const output = childProcess.execFileSync("powershell.exe", ["-NoProfile", "-Command", command], {
      encoding: "utf8",
      env: { ...process.env, SHOPBOT_LISTEN_HOST: String(host), SHOPBOT_LISTEN_PORT: String(port) },
      windowsHide: true,
    });
    return cleanText(output).trim() || null;
  } catch {
    return null;
  }
}

function listenFailureMessage(error, host, port, ownerLookup = listeningProcess) {
  let owner = null;
  try { owner = ownerLookup(host, port); } catch {}
  const code = cleanText(error && error.code || "UNKNOWN");
  return `shopbot dashboard listen failed: host=${host} port=${port} code=${code} owner=${owner || "none found on this address"}`;
}

function brandDiscoveryCommand(root, platform = process.platform) {
  const script = path.join(root, "engine", "discover-brands.py");
  return platform === "win32" ? { command: "py", args: ["-3", script] } : { command: "python3", args: [script] };
}

function scheduleBrandDiscovery(root, options = {}) {
  if (options.brandDiscovery === false) return () => {};
  let child = null;
  const run = () => {
    if (child) return;
    const invocation = brandDiscoveryCommand(root, options.platform);
    try {
      child = childProcess.spawn(invocation.command, invocation.args, { cwd: root, stdio: options.silent === true ? "ignore" : "inherit", windowsHide: true });
      child.once("error", () => { child = null; });
      child.once("close", () => { child = null; });
    } catch {
      child = null;
    }
  };
  run();
  const interval = Math.max(60_000, Number(options.brandDiscoveryIntervalMs) || BRAND_DISCOVERY_INTERVAL_MS);
  const timer = setInterval(run, interval);
  timer.unref();
  return () => {
    clearInterval(timer);
    if (child && !child.killed) child.kill();
    child = null;
  };
}

function latestWatchStatus(root) {
  try {
    const dir = path.join(root, "logs");
    const files = fs.readdirSync(dir).filter((f) => f.startsWith("watch-")).sort();
    if (!files.length) return { line: "no watcher runs yet", at: null };
    const file = files[files.length - 1];
    const txt = fs.readFileSync(path.join(dir, file), "utf8");
    const m = txt.match(/^(ALERT|NOALERT):.*$/m);
    return {
      line: cleanText(m ? m[0] : "run recorded, no status line"),
      at: file.replace("watch-", "").replace(".md", ""),
      alert: m ? m[0].startsWith("ALERT") : false,
    };
  } catch {
    return { line: "watcher logs unreadable", at: null, alert: false };
  }
}

function pinterestCorpus(corpusDir) {
  try {
    return fs
      .readdirSync(corpusDir)
      .filter((file) => /^clothes-\d+\.jpg$/i.test(file))
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
      .map((file, index) => ({
        id: file.replace(/\.jpg$/i, ""),
        title: `Pinterest reference ${index + 1}`,
        imageUrl: `/taste/corpus/${file}`,
        board: "Clothes",
        source: "pinterest",
      }));
  } catch {
    return [];
  }
}

function suggestionList(value) {
  return value && Array.isArray(value.suggestions)
    ? value.suggestions.filter((item) => item && typeof item === "object" && !Array.isArray(item))
    : [];
}

function trainingBatch(value, suggestions) {
  const byId = new Map(suggestions.map((item) => [item.id, item]));
  const sourceIds = value && Array.isArray(value.itemIds) ? value.itemIds : [];
  const seen = new Set();
  const itemIds = sourceIds.filter((id) => typeof id === "string" && !seen.has(id) && seen.add(id));
  const items = itemIds.map((id) => byId.get(id)).filter(Boolean);
  const missingIds = itemIds.filter((id) => !byId.has(id));
  const quotas = value && value.quotas && typeof value.quotas === "object" && !Array.isArray(value.quotas)
    ? Object.fromEntries(Object.entries(value.quotas).filter(([category, count]) => category && Number.isInteger(count) && count > 0))
    : {};
  return {
    version: Number.isInteger(value && value.version) ? value.version : 1,
    title: typeof (value && value.title) === "string" ? value.title : "Training batch",
    description: typeof (value && value.description) === "string" ? value.description : "",
    quotas,
    items,
    missingIds,
  };
}

function brandCandidateList(value) {
  return value && Array.isArray(value.candidates)
    ? value.candidates.filter((item) => item && typeof item === "object" && !Array.isArray(item) && typeof item.id === "string" && ID_RE.test(item.id))
    : [];
}

function clampVote(value) {
  if (!Number.isFinite(value)) return null;
  if (value < -2) return -2;
  if (value > 2) return 2;
  return Math.trunc(value);
}

function normalizedVotes(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result = {};
  for (const [id, entry] of Object.entries(value)) {
    const raw = entry && typeof entry === "object" ? entry.vote : entry;
    const vote = clampVote(raw);
    if (vote === null || vote === 0) continue;
    result[id] = {
      vote,
      ...(entry && typeof entry === "object" && typeof entry.at === "string" ? { at: entry.at } : {}),
    };
  }
  return result;
}

function normalizedOutcomes(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const allowed = new Set(OUTCOME_OPTIONS.map((option) => option.value));
  const result = {};
  for (const [id, entry] of Object.entries(value)) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry) || !allowed.has(entry.outcome)) continue;
    result[id] = {
      outcome: entry.outcome,
      ...(typeof entry.at === "string" ? { at: entry.at } : {}),
    };
  }
  return result;
}

function normalizedBrandDecisions(value, knownCandidates) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const allowed = new Set(BRAND_DECISION_OPTIONS.map((option) => option.value));
  const result = {};
  for (const [id, entry] of Object.entries(value)) {
    if (!knownCandidates.has(id) || !entry || typeof entry !== "object" || Array.isArray(entry) || !allowed.has(entry.decision)) continue;
    result[id] = {
      decision: entry.decision,
      ...(typeof entry.at === "string" ? { at: entry.at } : {}),
    };
  }
  return result;
}

function knownIds(paths) {
  const corpus = pinterestCorpus(paths.corpus);
  const suggestions = suggestionList(readJson(paths.suggestions, { suggestions: [] }));
  const ids = new Set(corpus.map((item) => item.id));
  for (const item of suggestions) {
    if (item && typeof item.id === "string") ids.add(item.id);
  }
  return ids;
}

function knownSuggestionIds(paths) {
  return new Set(suggestionList(readJson(paths.suggestions, { suggestions: [] })).map((item) => item.id).filter(Boolean));
}

function apiJson(res, status, payload, extraHeaders) {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    ...extraHeaders,
  });
  res.end(JSON.stringify(payload));
}

function atomicallyWriteJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = `${file}.${process.pid}.${Date.now()}.${Math.random().toString(16).slice(2)}.tmp`;
  try {
    fs.writeFileSync(temp, JSON.stringify(value, null, 2) + "\n", "utf8");
    try {
      fs.renameSync(temp, file);
    } catch (error) {
      // Windows does not replace an existing destination with renameSync.
      if (error && (error.code === "EEXIST" || error.code === "EPERM")) {
        if (fs.existsSync(file)) fs.unlinkSync(file);
        fs.renameSync(temp, file);
      } else {
        throw error;
      }
    }
  } finally {
    if (fs.existsSync(temp)) fs.unlinkSync(temp);
  }
}

function requestBody(req, res) {
  return new Promise((resolve, reject) => {
    const declared = Number(req.headers["content-length"] || 0);
    let total = 0;
    const chunks = [];
    let finished = false;
    const tooLarge = () => {
      if (finished) return;
      finished = true;
      apiJson(res, 413, { ok: false, error: "request body exceeds 8 KB" });
      req.resume();
      setTimeout(() => req.destroy(), 25);
      reject(new Error("body too large"));
    };
    if (declared > MAX_BODY_BYTES) {
      tooLarge();
      return;
    }
    req.on("data", (chunk) => {
      if (finished) return;
      total += chunk.length;
      if (total > MAX_BODY_BYTES) {
        tooLarge();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (finished) return;
      finished = true;
      resolve(Buffer.concat(chunks).toString("utf8"));
    });
    req.on("error", (error) => {
      if (finished) return;
      finished = true;
      reject(error);
    });
  });
}

function createServer(options = {}) {
  const root = options.root || ROOT;
  const paths = { ...DEFAULT_PATHS, ...(options.dataPaths || {}) };
  const corpusDir = paths.corpus || path.join(root, "taste", "corpus");
  const imagesDir = paths.productImages || path.join(root, "data", "images");
  let voteQueue = Promise.resolve();
  let outcomeQueue = Promise.resolve();
  let brandDecisionQueue = Promise.resolve();

  function state() {
    const suggestions = suggestionList(readJson(paths.suggestions, { suggestions: [] }));
    const training = trainingBatch(readJson(paths.trainingBatch, {}), suggestions);
    const pinterest = readJson(paths.pinterest, { status: "not-connected", boards: [] });
    const watches = readJson(paths.watches, { watches: [] }) || {};
    const taste = pinterestCorpus(corpusDir);
    const votes = normalizedVotes(readJson(paths.votes, {}));
    const outcomes = normalizedOutcomes(readJson(paths.outcomes, {}));
    const brandCandidates = brandCandidateList(readJson(paths.brandCandidates, { candidates: [] }));
    const crawlerReport = readJson(paths.crawlerReport, null);
    const ingestionData = readJson(paths.ingestionCandidates, { candidates: [], sources: [] });
    const ingestion = ingestionData && typeof ingestionData === "object" && !Array.isArray(ingestionData)
      ? {
          generatedAt: ingestionData.generatedAt || null,
          candidateCount: Array.isArray(ingestionData.candidates) ? ingestionData.candidates.length : 0,
          sources: Array.isArray(ingestionData.sources) ? ingestionData.sources : [],
        }
      : { generatedAt: null, candidateCount: 0, sources: [] };
    const candidateIds = new Set(brandCandidates.map((item) => item.id));
    const brandDecisions = normalizedBrandDecisions(readJson(paths.brandDecisions, {}), candidateIds);
    return {
      suggestions,
      trainingBatch: training,
      votes,
      outcomes,
      brandCandidates,
      brandDecisions,
      crawlerReport: crawlerReport && typeof crawlerReport === "object" && !Array.isArray(crawlerReport) ? crawlerReport : null,
      ingestion,
      pinterest,
      pinterestCorpus: taste,
      watches: Array.isArray(watches.watches) ? watches.watches : [],
      watcher: latestWatchStatus(root),
      voteScale: VOTE_SCALE,
      outcomeOptions: OUTCOME_OPTIONS,
      brandDecisionOptions: BRAND_DECISION_OPTIONS,
      tabs: {
        taste: { count: taste.length, items: taste },
        training: { count: training.items.length, items: training.items },
        suggestions: { count: suggestions.length, items: suggestions },
        brands: { count: brandCandidates.filter((item) => !brandDecisions[item.id]).length, items: brandCandidates },
      },
    };
  }

  function queueVote(id, vote) {
    const operation = voteQueue.then(() => {
      const votes = normalizedVotes(readJson(paths.votes, {}));
      if (vote === 0) delete votes[id];
      else votes[id] = { vote, at: new Date().toISOString() };
      atomicallyWriteJson(paths.votes, votes);
      return votes;
    });
    voteQueue = operation.catch(() => undefined);
    return operation;
  }

  function queueOutcome(id, outcome) {
    const operation = outcomeQueue.then(() => {
      const outcomes = normalizedOutcomes(readJson(paths.outcomes, {}));
      if (outcome === "none") delete outcomes[id];
      else outcomes[id] = { outcome, at: new Date().toISOString() };
      atomicallyWriteJson(paths.outcomes, outcomes);
      return outcomes;
    });
    outcomeQueue = operation.catch(() => undefined);
    return operation;
  }

  function queueBrandDecision(id, decision) {
    const operation = brandDecisionQueue.then(() => {
      const candidates = brandCandidateList(readJson(paths.brandCandidates, { candidates: [] }));
      const known = new Set(candidates.map((item) => item.id));
      const decisions = normalizedBrandDecisions(readJson(paths.brandDecisions, {}), known);
      if (decision === "none") delete decisions[id];
      else decisions[id] = { decision, at: new Date().toISOString() };
      atomicallyWriteJson(paths.brandDecisions, decisions);
      return decisions;
    });
    brandDecisionQueue = operation.catch(() => undefined);
    return operation;
  }

  const server = http.createServer(async (req, res) => {
    let url;
    try {
      url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
    } catch {
      res.writeHead(400, { "Cache-Control": "no-store" });
      res.end("bad request");
      return;
    }

    if (url.pathname === "/api/state" && req.method === "GET") {
      apiJson(res, 200, state());
      return;
    }

    if (url.pathname === "/api/vote") {
      if (req.method !== "POST") {
        apiJson(res, 405, { ok: false, error: "method not allowed" }, { Allow: "POST" });
        return;
      }
      if (String(req.headers["content-type"] || "").toLowerCase().split(";")[0].trim() !== "application/json") {
        apiJson(res, 415, { ok: false, error: "content-type must be application/json" });
        return;
      }
      try {
        const body = await requestBody(req, res);
        let input;
        try {
          input = JSON.parse(body);
        } catch {
          apiJson(res, 400, { ok: false, error: "invalid JSON" });
          return;
        }
        const id = input && input.id;
        const vote = input && input.vote;
        if (typeof id !== "string" || !ID_RE.test(id) || !knownIds({ ...paths, corpus: corpusDir }).has(id)) {
          apiJson(res, 400, { ok: false, error: "unknown or malformed id" });
          return;
        }
        if (typeof vote !== "number" || !Number.isInteger(vote) || ![-2, -1, 0, 1, 2].includes(vote)) {
          apiJson(res, 400, { ok: false, error: "vote must be an integer from -2 to 2" });
          return;
        }
        const votes = await queueVote(id, vote);
        apiJson(res, 200, { ok: true, votes });
      } catch (error) {
        if (res.writableEnded) return;
        apiJson(res, 500, { ok: false, error: cleanText(error.message || error) });
      }
      return;
    }

    if (url.pathname === "/api/outcome") {
      if (req.method !== "POST") {
        apiJson(res, 405, { ok: false, error: "method not allowed" }, { Allow: "POST" });
        return;
      }
      if (String(req.headers["content-type"] || "").toLowerCase().split(";")[0].trim() !== "application/json") {
        apiJson(res, 415, { ok: false, error: "content-type must be application/json" });
        return;
      }
      try {
        const body = await requestBody(req, res);
        let input;
        try {
          input = JSON.parse(body);
        } catch {
          apiJson(res, 400, { ok: false, error: "invalid JSON" });
          return;
        }
        const id = input && input.id;
        const outcome = input && input.outcome;
        const allowed = new Set(["none", ...OUTCOME_OPTIONS.map((option) => option.value)]);
        if (typeof id !== "string" || !ID_RE.test(id) || !knownSuggestionIds(paths).has(id)) {
          apiJson(res, 400, { ok: false, error: "unknown or malformed suggestion id" });
          return;
        }
        if (typeof outcome !== "string" || !allowed.has(outcome)) {
          apiJson(res, 400, { ok: false, error: "unknown outcome" });
          return;
        }
        const outcomes = await queueOutcome(id, outcome);
        apiJson(res, 200, { ok: true, outcomes });
      } catch (error) {
        if (res.writableEnded) return;
        apiJson(res, 500, { ok: false, error: cleanText(error.message || error) });
      }
      return;
    }

    if (url.pathname === "/api/brand-decision") {
      if (req.method !== "POST") {
        apiJson(res, 405, { ok: false, error: "method not allowed" }, { Allow: "POST" });
        return;
      }
      if (String(req.headers["content-type"] || "").toLowerCase().split(";")[0].trim() !== "application/json") {
        apiJson(res, 415, { ok: false, error: "content-type must be application/json" });
        return;
      }
      try {
        const body = await requestBody(req, res);
        let input;
        try {
          input = JSON.parse(body);
        } catch {
          apiJson(res, 400, { ok: false, error: "invalid JSON" });
          return;
        }
        const id = input && input.id;
        const decision = input && input.decision;
        const candidates = brandCandidateList(readJson(paths.brandCandidates, { candidates: [] }));
        const known = new Set(candidates.map((item) => item.id));
        const allowed = new Set(["none", ...BRAND_DECISION_OPTIONS.map((option) => option.value)]);
        if (typeof id !== "string" || !ID_RE.test(id) || !known.has(id)) {
          apiJson(res, 400, { ok: false, error: "unknown or malformed brand candidate id" });
          return;
        }
        if (typeof decision !== "string" || !allowed.has(decision)) {
          apiJson(res, 400, { ok: false, error: "unknown brand decision" });
          return;
        }
        const brandDecisions = await queueBrandDecision(id, decision);
        apiJson(res, 200, { ok: true, brandDecisions });
      } catch (error) {
        if (res.writableEnded) return;
        apiJson(res, 500, { ok: false, error: cleanText(error.message || error) });
      }
      return;
    }

    if (url.pathname.startsWith("/product-images/")) {
      const file = path.basename(url.pathname);
      const match = IMAGE_RE.exec(file);
      const imagePath = path.join(imagesDir, file);
      if (match && fs.existsSync(imagePath)) {
        res.writeHead(200, {
          "Content-Type": IMAGE_TYPES[match[1].toLowerCase()],
          "Cache-Control": "private, max-age=3600",
        });
        fs.createReadStream(imagePath).pipe(res);
        return;
      }
    }

    if (url.pathname.startsWith("/taste/corpus/")) {
      const file = path.basename(url.pathname);
      const imagePath = path.join(corpusDir, file);
      if (/^clothes-\d+\.jpg$/i.test(file) && fs.existsSync(imagePath)) {
        res.writeHead(200, {
          "Content-Type": "image/jpeg",
          "Cache-Control": "private, max-age=3600",
        });
        fs.createReadStream(imagePath).pipe(res);
        return;
      }
    }

    if (url.pathname === "/" || url.pathname === "/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(fs.readFileSync(path.join(__dirname, "index.html")));
      return;
    }

    res.writeHead(404, { "Cache-Control": "no-store" });
    res.end("not found");
  });
  server.dashboardOptions = { root, paths: { ...paths, corpus: corpusDir, productImages: imagesDir } };
  return server;
}

function start(options = {}) {
  const server = createServer(options);
  const port = options.port === undefined ? PORT : options.port;
  const host = options.host || "127.0.0.1";
  return new Promise((resolve, reject) => {
    const onError = (error) => {
      server.off("listening", onListening);
      error.dashboardHost = host;
      error.dashboardPort = port;
      if (options.silent !== true) {
        console.error(listenFailureMessage(error, host, port));
        error.dashboardReported = true;
      }
      reject(error);
    };
    const onListening = () => {
      server.off("error", onError);
      const stopBrandDiscovery = scheduleBrandDiscovery(options.root || ROOT, options);
      server.once("close", stopBrandDiscovery);
      resolve(server);
    };
    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(port, host, () => {
      if (options.silent !== true) {
        const address = server.address();
        const shownPort = address && typeof address === "object" ? address.port : port;
        console.log(`shopbot dashboard -> http://${host}:${shownPort}`);
      }
    });
  });
}

if (require.main === module) {
  start().catch((error) => {
    if (!error.dashboardReported) console.error(listenFailureMessage(error, error.dashboardHost || "127.0.0.1", error.dashboardPort || PORT));
    process.exitCode = 1;
  });
}

module.exports = { createServer, start, VOTE_SCALE, normalizedVotes, normalizedBrandDecisions, trainingBatch, brandDiscoveryCommand, listenFailureMessage };
