// shopbot dashboard server — zero dependencies, personal-first.
// Serves the dashboard UI and a tiny JSON API; votes persist into taste/votes.json
// which the /shop scout reads as taste signal.
//   node dashboard/server.js   →  http://localhost:7877
const http = require("http");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const PORT = 7877;

const FILES = {
  suggestions: path.join(ROOT, "data", "suggestions.json"),
  votes: path.join(ROOT, "taste", "votes.json"),
  pinterest: path.join(ROOT, "config", "pinterest.json"),
  watches: path.join(ROOT, "config", "watches.json"),
};

function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return fallback;
  }
}

function cleanText(value) {
  return String(value || "")
    .replace(/â€”/g, "-")
    .replace(/â‰ˆ/g, "~")
    .replace(/â‰¤/g, "<=")
    .replace(/â/g, "-")
    .replace(/â/g, "~")
    .replace(/â¤/g, "<=")
    .replace(/[^\x20-\x7E]/g, "");
}

function latestWatchStatus() {
  try {
    const dir = path.join(ROOT, "logs");
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
    return { line: "watcher logs unreadable", at: null };
  }
}

function pinterestCorpus() {
  try {
    const dir = path.join(ROOT, "taste", "corpus");
    return fs
      .readdirSync(dir)
      .filter((file) => /^clothes-\d+\.jpg$/i.test(file))
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
      .map((file, index) => ({
        id: file.replace(".jpg", ""),
        title: `Pinterest reference ${index + 1}`,
        imageUrl: `/taste/corpus/${file}`,
        board: "Clothes",
        source: "pinterest",
      }));
  } catch {
    return [];
  }
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname === "/api/state") {
    const state = {
      suggestions: readJson(FILES.suggestions, { suggestions: [] }).suggestions,
      votes: readJson(FILES.votes, {}),
      pinterest: readJson(FILES.pinterest, { status: "not-connected", boards: [] }),
      pinterestCorpus: pinterestCorpus(),
      watches: readJson(FILES.watches, { watches: [] }).watches,
      watcher: latestWatchStatus(),
    };
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(state));
    return;
  }

  if (url.pathname === "/api/vote" && req.method === "POST") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const { id, vote } = JSON.parse(body); // vote: 1 | -1 | 0 (clear)
        if (typeof id !== "string" || ![1, -1, 0].includes(vote)) throw new Error("bad input");
        const votes = readJson(FILES.votes, {});
        if (vote === 0) delete votes[id];
        else votes[id] = { vote, at: new Date().toISOString() };
        fs.mkdirSync(path.dirname(FILES.votes), { recursive: true });
        fs.writeFileSync(FILES.votes, JSON.stringify(votes, null, 2));
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true, votes }));
      } catch (e) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: String(e.message || e) }));
      }
    });
    return;
  }

  if (url.pathname.startsWith("/taste/corpus/")) {
    const file = path.basename(url.pathname);
    const imagePath = path.join(ROOT, "taste", "corpus", file);
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

  res.writeHead(404);
  res.end("not found");
});

server.listen(PORT, "127.0.0.1", () =>
  console.log(`shopbot dashboard → http://localhost:${PORT}`)
);
