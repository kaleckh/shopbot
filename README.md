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
