# shopbot

Kale's fashion/shopping agent. **Personal tool first, product later** — everything is built
so the engine can be lifted behind a web surface once it's proven on daily personal use.

## Architecture — three stacked layers

```
┌──────────────────────────────────────────────────────┐
│ 3. AGENT (later): "I need boots for winter" →        │
│    research → compare → watch → checkout assist      │
├──────────────────────────────────────────────────────┤
│ 2. SCOUT + TASTE: /shop find <query> — fans out      │
│    across retailers, ranks candidates against the    │
│    style profile (config/profile.json)               │
├──────────────────────────────────────────────────────┤
│ 1. WATCHER (live): scheduled price/stock checks of   │
│    config/watches.json → Desktop DEAL-ALERT.md       │
└──────────────────────────────────────────────────────┘
```

## Components

- `config/watches.json` — the watch list. Each entry: `id`, natural-language `goal`,
  `maxPriceUSD`, `checkUrls`, `notes`. Adding a watch = adding a JSON entry.
- `config/profile.json` — the style/taste profile: sizes, fit, brands, budgets, no-gos.
  The scout layer scores every candidate against this. This file IS the personalization.
- `engine/discover-brands.py` — automatically mines trusted multi-brand retailer feeds for
  previously unknown menswear labels, ranks them against taste signals, and publishes
  representative products to `data/brand-candidates.json`.
- `engine/scout-browser.py` — runs Shopbot's self-hosted Crawl4AI browser, accepts products
  only when a configured official men's category page links the PDP, then publishes
  deterministically extracted price, variant stock, provenance, and locally cached
  photography. Per-source catalogue policy balances categories, applies review-queue
  backpressure, learns from votes, and records crawl/filter metrics in
  `data/crawler-last-run.json`. Generic extraction covers Product/ProductGroup JSON-LD,
  nested JSON app state, Open Graph/itemprop/rendered price data, canonical/protocol-relative
  URLs, and sale prices. PDP verification always bypasses cache; category discovery can be
  forced fresh with `npm run scout:web -- --fresh`.
- `engine/source-ingest.py` — normalizes public sitemap indexes plus JSON, CSV, and XML
  merchant/affiliate feeds into one local lead registry. It enforces HTTPS host/path gates,
  bounded traversal and pagination, environment-only feed secrets, atomic last-good
  preservation, and never labels feed metadata as PDP-verified. See
  `docs/SOURCE_ADAPTERS.md`; run `npm run ingest:sources`.
- `taste/brand-decisions.json` — the current profile's follow, occasional, reject, and
  too-expensive decisions. The shared candidate registry stays separate from user taste.
- `data/training-batch.json` — a fixed, balanced 30-item menswear curriculum used by the
  dashboard Training tab. It references catalog item IDs so votes stay attached to the same
  products while the larger Suggestions queue changes.
- `engine/price-watch.ps1` — headless Claude run that checks every watch and drops
  `DEAL-ALERT.md` on the Desktop on a hit. Scheduled as Windows task `ClaudePriceWatch`
  (9:23 AM + 4:23 PM daily). Logs to `logs/` (gitignored, last 20 kept).
- `/shop` Claude Code skill (`~/.claude/skills/shop/`) — the interactive surface:
  `find` (scout + rank), `watch` (add to watch list), `deals` (latest watcher report),
  `profile` (view/update taste profile).

## Design rules

1. **Config is the product.** All personalization lives in JSON the engine reads — no
   hardcoded taste. Productizing = swapping file paths for per-user rows.
2. **LLM judges, retailers lie.** Price trackers and deal articles are treated as leads,
   never as truth — the watcher verifies on an actual retailer page before alerting
   (first live run caught a tracker showing $166 for a drive that really cost $419).
3. **Alerts must be rare and real.** A Desktop alert means "buy now." False alerts kill
   trust in the whole system.
4. **ASCII-only .ps1 files** — PowerShell 5.1 parse-breaks on BOM-less UTF-8 scripts.

## Status

- 2026-07-06: repo created. Watcher layer live and end-to-end tested (first watch:
  quality 2TB NVMe <= $170 during the NAND shortage). Profile template created,
  /shop skill installed. Next: fill profile via intake session, first real
  fashion watches, scout-mode iteration.
- 2026-07-06: Pinterest account `https://www.pinterest.com/kaleckh/` synced into
  `taste/corpus/` with 50 Clothes-board images. Dashboard serves the local taste
  board at `http://localhost:7877` and persists likes/dislikes to `taste/votes.json`.
- 2026-09-01: Brand discovery is live. The dashboard refreshes a trusted-retailer discovery
  job at startup and every six hours, then presents new labels with three representative
  products and profile-specific decisions under **Discover brands**.
- 2026-09-01: Blocked-site retrieval moved to a Shopbot-owned Crawl4AI browser and local
  persistent profile. It rendered five Zara men's categories, discovered 168 unique PDPs,
  and deterministically extracted Zara's ProductGroup data without an API key or paid
  retrieval service. Run `npm run crawler:setup` once, then `npm run scout:web`.
- 2026-09-01: The generalized source contract also rendered American Eagle's official men's
  jeans category, discovered 60 eligible PDPs, and published 12 fresh Product JSON-LD cards.
  The active browser catalogue is now 36/36 across Zara and American Eagle.
- 2026-09-01: Declarative source ingestion now covers XML sitemaps and JSON/CSV/XML product
  feeds. The first full public-sitemap run traversed 111 Levi's sitemap documents, found
  4,232 raw product URLs, and retained 781 canonical US menswear candidates as leads.
