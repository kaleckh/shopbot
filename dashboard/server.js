// Shopbot dashboard server - zero dependencies, personal-first.
// Serves the dashboard UI and a tiny JSON API; votes persist into taste/votes.json.
//   node dashboard/server.js -> http://localhost:7877
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PORT = 7877;
const MAX_BODY_BYTES = 8 * 1024;
const ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const VOTE_SCALE = [
  { value: -2, label: "Strong dislike", shortLabel: "-2" },
  { value: -1, label: "Dislike", shortLabel: "-1" },
  { value: 0, label: "Neutral / clear", shortLabel: "0" },
  { value: 1, label: "Like", shortLabel: "+1" },
  { value: 2, label: "Strong like", shortLabel: "+2" },
];

const DEFAULT_PATHS = {
  suggestions: path.join(ROOT, "data", "suggestions.json"),
  votes: path.join(ROOT, "taste", "votes.json"),
  pinterest: path.join(ROOT, "config", "pinterest.json"),
  watches: path.join(ROOT, "config", "watches.json"),
  corpus: path.join(ROOT, "taste", "corpus"),
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

function knownIds(paths) {
  const corpus = pinterestCorpus(paths.corpus);
  const suggestions = suggestionList(readJson(paths.suggestions, { suggestions: [] }));
  const ids = new Set(corpus.map((item) => item.id));
  for (const item of suggestions) {
    if (item && typeof item.id === "string") ids.add(item.id);
  }
  return ids;
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
  let voteQueue = Promise.resolve();

  function state() {
    const suggestions = suggestionList(readJson(paths.suggestions, { suggestions: [] }));
    const pinterest = readJson(paths.pinterest, { status: "not-connected", boards: [] });
    const watches = readJson(paths.watches, { watches: [] }) || {};
    const taste = pinterestCorpus(corpusDir);
    const votes = normalizedVotes(readJson(paths.votes, {}));
    return {
      suggestions,
      votes,
      pinterest,
      pinterestCorpus: taste,
      watches: Array.isArray(watches.watches) ? watches.watches : [],
      watcher: latestWatchStatus(root),
      voteScale: VOTE_SCALE,
      tabs: {
        taste: { count: taste.length, items: taste },
        suggestions: { count: suggestions.length, items: suggestions },
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
  server.dashboardOptions = { root, paths: { ...paths, corpus: corpusDir } };
  return server;
}

function start(options = {}) {
  const server = createServer(options);
  const port = options.port === undefined ? PORT : options.port;
  const host = options.host || "127.0.0.1";
  return new Promise((resolve, reject) => {
    const onError = (error) => {
      server.off("listening", onListening);
      reject(error);
    };
    const onListening = () => {
      server.off("error", onError);
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
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { createServer, start, VOTE_SCALE, normalizedVotes };
