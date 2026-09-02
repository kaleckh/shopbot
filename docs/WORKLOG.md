# Worklog

## 2026-09-01 - Balanced training curriculum

- Added a dedicated Training tab backed by a stable 30-item catalog manifest: 6 pants, 6 outerwear, 6 tops, 6 knits, 4 shoes, and 2 accessories across 25 brands.
- Kept completed cards in place and exposed live rated progress so voting does not silently remove or reshuffle the curriculum.
- Removed the false default-neutral selection from unvoted cards; `0` now clearly means “Clear vote.”
- Verified 1,357 dashboard assertions, the exact category quotas, 30 unique/resolvable IDs, no browser console errors, and the rendered 30-card tab in Chrome.

## 2026-09-01 - Declarative catalog ingestion

- Added a dependency-free source ingestion CLI with bounded sitemap recursion, gzip sitemap support, JSON/CSV/XML feed mappings, bounded page templates, environment-only auth headers, response-size limits, transient retries, source URL gates, normalized lead evidence, atomic publication, and last-good/partial-scan preservation.
- Configured Levi's public US sitemap as the first blocked-storefront discovery route. The full run read 111 sitemap documents, parsed 4,232 raw product URLs, and retained 781 canonical US menswear candidates with product IDs, images, and last-modified dates.
- Added a compact ingestion health/count object to the dashboard API and header. Detailed candidates stay in `data/ingestion-candidates.json`; none are mislabeled as price- or stock-verified.
- Verified 23 focused source-ingestion checks before the full regression pass.

## 2026-09-01 - Firecrawl Zara Ingestion

- Added a provider-backed blocked-site scout with official-host/path validation, men's-category audience evidence, deterministic PDP product extraction, shared exclusion rules, local image caching, atomic idempotent publication, bounded transient retries, rate-limit circuit breaking, and safe preservation on total failure.
- Replaced the temporary six-item global cap with per-source adaptive policy: bootstrap 24, unreviewed backpressure 24, eight later additions, active ceiling 50, four-per-category diversity pressure, positive-vote refresh priority, and vote-derived category/signal weights.
- Converted Zara from `search-then-pdp`/blocked to the working `firecrawl-search-product` contract. A live run found 119 unique PDPs and expanded the dashboard from six to 17 verified Zara US menswear cards. A later anonymous run hit HTTP 429; it published nothing and preserved all 17 cards.
- Added `data/firecrawl-last-run.json` and a dashboard catalogue chip for active/target progress and rate-limit state. The report captures discovery, filter reasons, category eligibility/selection, attempts, requests, provider-reported credits, and publication.
- Replaced the active Firecrawl integration with Shopbot's pinned, self-hosted Crawl4AI browser. A live dry-run rendered five official Zara men's categories, discovered 168 unique PDPs, and verified deterministic ProductGroup extraction. The local profile and Crawl4AI cache avoid repeated remote work; no provider API key or per-page billing remains.
- Generalized the browser engine across Product/ProductGroup JSON-LD, nested JSON app state, Open Graph/itemprop/rendered price data, canonical and protocol-relative URLs, sale prices, fresh PDP verification, poisoned-cache recovery, transport retries, source-contract validation, extraction-method metrics, and aggregate multi-source dashboard status. American Eagle proved the generic path with 60 eligible men's PDPs and 12 freshly verified cards at $24.97-$41.97. Live probes preserve explicit blocks for Uniqlo, Levi's, Urban Outfitters, and Patagonia.
- Fixed hoodie jackets being classified as knit by making explicit outerwear terms win before hoodie/knit terms.
- Verified 23 source-ingestion checks, 68 focused browser-scout assertions, 23 scout assertions, 15 brand-discovery assertions, and 1,350 dashboard assertions. The active browser catalogue holds 24 Zara and 12 American Eagle records.

## 2026-09-01

- Published the local repo to GitHub as `kaleckh/shopbot` (`https://github.com/kaleckh/shopbot`) and pushed outstanding local work: Shopify scout, sources roster, cached product images, dashboard/suggestion updates, and the `ClaudePriceWatch` registration script.
- Reworked the dashboard into an actionable learning loop: full-width layout, unvoted review queue, distinct lead/verified/expired states, `+2` verification queue, personalized ranking after 15 suggestion votes, and atomic purchase-outcome storage.
- Normalized the scout-produced catalogue from 62 ambiguous `other` records to 7 and replaced near-universal mode tags with title/product-derived modes. Added `npm run normalize:catalogue` and a focused classifier regression.
- Removed ten women's products from mixed-gender Edwin, Marine Layer, Outerknown, and A.P.C. feeds that leaked through title-only filtering. The scout now checks full product metadata and source-specific exclusions before publishing menswear suggestions.
- Shipped the first automatic brand-discovery loop: trusted multi-brand feeds produced 25 new candidate labels with cached representative products and evidence. Added the Discover Brands queue, atomic profile decisions, recovery filters, six-hour background refresh, transport fallback for retailer WAFs, and focused engine/API/browser verification.
- Labeled first-pass brand matches as exploratory after auditing the source skew: Blue Owl, Okayama Denim, and Standard & Strange make the queue heavily Japanese-denim oriented while the profile has only one product vote. Added Zara as a followed source through its official US men's collection; the collection is search-indexed but returns HTTP 403 to direct automation, so it uses search-to-PDP discovery.
- Fed brand decisions back into later discovery scores: follow and occasional reinforce matched style signals, reject suppresses them, and too-expensive remains separate from style. Following Zara now teaches loose, relaxed, carpenter, textured, and minimal without falsely treating its price as taste.

## 2026-08-17 (fetch methods)

- Corrected the constraint: we do not only use HTML storefronts. Brand-site HTML failed; Shopify JSON is the niche volume path; stocking retailers are how blocked giants stay in scope.
- ShopWSS `products.json` works (Nike/Jordan/Converse). Zappos product pages render (Levi 568 Loose Straight, $110, sizes 29-38). Nordstrom PDPs currently return empty. Guessed Uniqlo commerce APIs timed out.
- Published the Zappos Levi 568 as a verified retailer-direct record so the #1 board garment is not missing just because levi.com 403s.

## 2026-08-17 (later)

- Probed ~100 Shopify storefronts. Roster is now 54 sources / 42 working. New working names include Filson, Ben Davis, Folk, Drake's, Universal Works, YMC, Wax London, Story mfg., Noah, Iron Heart, 3sixteen, Left Field, Railcar, Okayama Denim, Blue Owl, Standard & Strange, plus streetwear (Stussy, Kith, ALD).
- Scout now uses the product `vendor` as the brand so multi-brand shops (Okayama, Blue Owl) mint real mill names (Samurai, Momotaro, Japan Blue).
- Published a large lead wave, then stripped junk: Norse DKK-as-USD prices, Snow Peak tents/duffels, women's, slim, socks, neon signs. Catalogue is **206 cards / 62 brands**. Still leads, not PDPs.

## 2026-08-17

## 2026-08-15

- Added the ASCII-only Windows PowerShell 5.1 registration script and restored `ClaudePriceWatch` as an enabled, ready task. It invokes `engine/price-watch.ps1` through `powershell.exe -File` with daily triggers at 9:23 AM and 4:23 PM; the first scheduled run is 2026-08-16 9:23 AM local. Registration did not start the task or run Claude.
- Made suggestion verification status age-aware in the browser. Missing or more-than-seven-day-old `checkedAt` values now render and filter as `stale` without rewriting `data/suggestions.json`; the chip, evidence detail, and Verification filter share the same effective-status function.
- Added exact-bind listen diagnostics. A failed `127.0.0.1:7877` bind now reports host, port, code, and the process owning that exact loopback tuple; the live check identified `node.exe` PID 9648, without treating Tailscale listeners as the dashboard or restarting either service.
- `npm test` passed: the watcher ownership regression passed and the dashboard suite completed 216 assertions with zero failures.

## 2026-08-07 (later)

- Kale declined the profile intake and redirected the product: he wants volume to react to, not a profile to fill in. Recorded as a decision rather than a deferral, since it inverts which signal the scout leans on.
- Batch 8 -> 26 across shoes, accessories, outerwear and pants, $19.99 to $288, every item with a cached photo. The first batch was all shoes and accessories while the board is mostly outerwear, knits and bottoms.
- The 18 new records publish as `lead`: prices came off brand collection grids rather than product pages, several as ranges across sizes, so `priceUSD` holds the low end and `evidence` says so. Verify on vote.
- Restructured the suggestion card for browsing — photo, price and a verified/lead chip stay visible, everything else moved behind one disclosure. Twenty-six cards each carrying an inline evidence block is not something a person can look through.

## 2026-08-07

- Cached product photography for all eight suggestions into `data/images/` and added a guarded `/product-images/` route. Every card had shipped with `imageUrl: null`, which made a fashion-voting surface unusable and is the most likely reason the batch sat at zero votes. Photos are cached rather than hotlinked because retailer CDNs reject cross-origin referers and rotate URLs. Suite grows to 130 assertions, including one that every published `imageUrl` actually resolves.
- Verified the cached photos by eye against the products they claim to be. Seven are correct and full-size; the Converse entry is a correct but 78px colorway swatch, recorded in that record's `imageNote` rather than shipped silently.
- Finished the taste extraction: images 37-50 had never been individually reviewed, so the prior had been built on 36 of 50. Four corrections came out of the tail — roughly 1 in 8 corpus images is a mood/photography/hair pin and carries no product signal; green and rust are accent colors the first pass missed entirely; the board's answer to "corporate-presentable" is wide pleated trousers, so the old `dress shirts/suiting` no-go would have made the scout reject the right item; and footwear tightened to Chuck 70 with cream foxing and Jordan 1 high.
- Updated the `/shop` skill, which had drifted into being actively wrong: it described the v1 schema, called votes up/down, and offered `Start-ScheduledTask -TaskName ClaudePriceWatch` for a task that no longer exists.

## 2026-08-06

- Replaced the flat dashboard grid with accessible Taste and Suggestions tabs, persistent URL/localStorage tab state, five-level roving vote controls, responsive layout, verification/provenance details, and shareable client-side suggestion filters. Implementation delegated to GPT-5.6 Luna against a written spec, then reviewed.
- Refactored the dashboard server for injectable data paths, API no-store responses, strict known-ID and vote validation, tolerant vote normalization, serialized atomic vote publication, and safe request-size handling.
- Added the dependency-free dashboard HTTP test suite (92 assertions) and split package scripts so the watcher and dashboard regressions are separately attributable.
- Review fixes on top of the delegated work: the fixed-option filter selects did not sync from a shared `?status=...` URL, so the controls disagreed with the filtered list; the taste-count assertion was pinned to a literal 50 and would have failed the moment the Pinterest corpus grew; and the suite reported a hardcoded "1 passed" regardless of how many checks ran.
- Published the first schema v2 suggestion batch: eight shoe and accessory candidates, each priced from a live retailer page read on 2026-08-06, each carrying match reasons, provenance, evidence, and verification time. nike.com, newbalance.com, converse.com, and END refused automated reads, so those candidates are priced from stocking retailers with the substitution recorded per record.
- Re-pinned the Control Tower health contract to two required checks. Direct evaluation reports `healthy` with both passing; the `tower health shopbot --run` CLI path is blocked upstream by an unrelated `project:unreal-copilot` registry failure.
- Confirmed while updating next steps that `ClaudePriceWatch` is no longer registered and the newest watcher log is 2026-07-19.

## 2026-07-13

- Registered Shopbot with Control Tower and added the standard durable project-memory and authority files before repairing the recurring watcher log-lock defect.
- Replaced live writes to the final watcher report with private capture plus atomic publication. A Windows PowerShell 5.1 regression proves the final `watch-*.md` is absent during producer execution, appears only after close, preserves output, cleans temporary files, and does not emit a false alert.
- Removed the large inline watch-config payload from Claude's command arguments. The watcher now validates `config/watches.json` locally and supplies its exact path as the source of truth; the regression rejects copied JSON and requires the expected path.
- Added a dependency-free `npm test` entry and hash-pinned Control Tower health contract. `tower health shopbot --run` executed the watcher regression and reported the project healthy.
