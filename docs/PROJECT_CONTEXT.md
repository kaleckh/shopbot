# Project Context

## Summary

Shopbot is Kale's personal fashion and shopping agent. Its live watcher verifies configured retailer pages for price and stock conditions, while taste-driven scouting and a future conversational agent build on the same JSON configuration.

## Stack and Repository Map

- Windows PowerShell 5.1 watcher: `engine/price-watch.ps1`
- Watch, profile, and scout-source configuration: `config/` (`sources.json` is the brand/retailer roster; `engine/scout-shopify.py` pulls volume from Shopify `products.json`)
- Taste corpus, votes, brand decisions, and post-purchase outcomes: `taste/`
- Automatic brand discovery: `engine/discover-brands.py` mines trusted multi-brand retailers into `data/brand-candidates.json`; the dashboard server refreshes it at startup and every six hours.
- Blocked-site product ingestion: `engine/scout-browser.py` runs a local Crawl4AI browser with a persistent gitignored profile. Configured official men's category pages provide the audience boundary; only their same-host PDP links are eligible. Generic deterministic extraction covers Product/ProductGroup JSON-LD, nested JSON app state, Open Graph/itemprop/rendered price data, canonical/protocol-relative URLs, availability, and sale prices without an LLM. Zara US and American Eagle are proven sources with 24 and 12 active cards respectively.
- Catalog-source ingestion: `engine/source-ingest.py` provides declarative `sitemap-xml`, `json-feed`, `csv-feed`, and `xml-feed` adapters and publishes normalized discovery leads to `data/ingestion-candidates.json`. The dashboard exposes only its count and source health. Levi's is the live sitemap proof with 781 canonical US menswear leads from 111 public sitemap documents; these are not price/stock verified.
- Local dashboard: `dashboard/` (taste references, a fixed balanced training curriculum, retail review, and brand-discovery queues with verification, outcome tracking, and personalized sorting after 15 suggestion votes)
- Runtime data and logs: `data/`, `logs/`
- Verification: `npm test` (`test:watcher` + `test:dashboard` + `test:scout` + `test:brands` + `test:web`); Control Tower owns the hash-pinned `watcher-regression` and `dashboard-regression` health checks.

## Constraints

- PowerShell scripts are ASCII-only for Windows PowerShell 5.1 compatibility.
- A deal alert is actionable only after retailer-page verification.
- Scheduled runs must not hold the content log open while another process writes or replaces it.
- The watcher validates `config/watches.json` locally and passes only its exact path to the producer, preventing command-line prompt truncation as the watch list grows.
- Testing must avoid false alerts and unintended purchases.
- Dashboard data is dependency-free browser HTML/JS served by the local Node server; discovery leads never imply fresh price or stock, and only retailer-page evidence can be `verified`.
- The suggestion catalogue is menswear-focused. Shopify ingestion enforces that boundary from merchant metadata and source exclusions, not by inferring a model's gender from product photography.
- Browser ingestion requires an allowed HTTPS host, a configured official men's category URL, and a PDP link rendered inside that category page. A directly supplied PDP cannot bypass this audience gate.
- Feed and sitemap ingestion also requires HTTPS allowlists and path gates, bounded traversal, and environment-referenced secrets. Its output remains `lead` evidence until a current PDP or authorized retailer verifies price and stock.
- Browser run accounting distinguishes logical requests, attempts, cache hits, and extraction methods. `data/crawler-last-run.json` records discovery breadth, category selection, rejection reasons, publication, blocks, failures, and backpressure; the dashboard aggregates progress across all sources in the latest run. PDP verification always fetches fresh content, while category discovery is cacheable and supports an explicit `--fresh` bypass.

## Current Priority

Complete the balanced Training batch before judging recommendation quality, then work through the unvoted Suggestions and Discover Brands queues. Product and brand decisions teach separate but connected signals; source expansion now happens through the automatic discovery loop rather than requiring known store URLs.
