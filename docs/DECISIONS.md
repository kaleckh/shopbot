# Decisions

## 2026-09-01 - Separate Catalog Discovery Adapters from Purchase Verification

- Context: Retailers expose catalogs through different surfaces. Some render categories, some publish XML sitemaps, and sanctioned affiliate programs commonly provide JSON, CSV, or XML feeds. Treating every source as an HTML page either loses coverage or encourages brittle access-control evasion.
- Decision: Add one declarative discovery boundary for `sitemap-xml`, `json-feed`, `csv-feed`, and `xml-feed`. Every adapter emits the same local candidate contract with source, URL, optional SKU/image/price/availability, observation time, and explicit `lead` evidence. Existing Shopify and rendered-browser paths remain compatible specialist consumers.
- Safety and failure behavior: Accept HTTPS only; enforce source host/path gates; bound recursion, pagination, response size, retries, and pacing; reference feed credentials only by environment-variable name; publish atomically; preserve last-good data on failure and retain unseen prior records after a partial sitemap scan. CAPTCHA solving, identity rotation, and access-control bypass are not adapter capabilities.
- Proof: Levi's public US sitemap index declared 110 product shards. A full local run read 111 sitemap documents, parsed 4,232 raw URLs, and accepted 781 canonical men's product candidates with images and last-modified dates. They remain leads because sitemap evidence has no current price or stock.

## 2026-09-01 - Generalize the Owned Browser into a Declarative Retailer Contract

- Context: Zara proved self-hosted retrieval but its ProductGroup markup, URL shapes, and images are not universal. A useful crawler must onboard other retailers without cloning the orchestration or weakening evidence and freshness rules.
- Decision: Keep retailer differences in `config/sources.json` (allowed hosts, men's category URLs, audience/PDP path patterns, pacing, categories, and catalogue policy) while the engine handles common public-commerce representations: Product/ProductGroup JSON-LD, nested JSON app state, Open Graph/itemprop/rendered price data, canonical and protocol-relative URLs, availability, and sale prices. Product verification always bypasses cache; category discovery may use cache unless `--fresh` is requested.
- Failure behavior: Validate every source contract before launching a browser. Retry transient browser failures once with a cache bypass, reject tiny or challenge content, stop a source on an access block, catch per-page extraction failures, publish atomically, and preserve the last good catalogue. CAPTCHA, login, and proxy/identity rotation remain outside the contract.
- Proof: The same engine rendered American Eagle's official men's jeans category, discovered 60 eligible PDPs, and published 12 fresh cards through generic Product JSON-LD extraction. Zara remains at 24 cards through ProductGroup extraction. The dashboard now aggregates source targets and active counts.

## 2026-09-01 - Own Blocked-Storefront Retrieval, with an Explicit Audience Gate

- Context: Zara's official US catalogue is useful for the current taste profile but rejects direct automated HTTP with a 403. A search query containing “men” is not proof that an individual gender-neutral PDP belongs to the men's catalogue.
- Decision: Run a pinned Crawl4AI browser locally with a persistent gitignored profile. Configured official men's category pages contribute PDPs only when the rendered link stays on the allowed HTTPS host; deterministic Product/ProductGroup JSON-LD or standard product metadata must provide price and variants. Store category URL/title as audience evidence, cache product images locally, and publish PDP-derived prices and variant availability as `verified`.
- Why: Shopbot owns the retrieval runtime, data, cache, and pacing without per-page billing or provider rate limits. The category-to-product evidence chain prevents a directly supplied PDP from silently weakening the menswear boundary.
- Consequences: `npm run crawler:setup` installs the pinned browser runtime once; `npm run scout:web` refreshes configured sources idempotently and preserves the last good catalogue on total failure. Zara's five configured men's category pages exposed 168 unique PDPs in a live dry-run. Each source retains its adaptive policy: Zara bootstraps toward 24 active cards with four-per-category diversity pressure, pauses at 24 unreviewed cards, adds at most eight after bootstrap, refreshes positive votes first, and has a 50-item active ceiling. Strong rejects and out-of-stock records leave the active count without deleting review history.
- Observability: The latest run report separates discovered PDPs, pre- and post-extraction rejection reasons, eligible and selected category counts, logical requests, attempts, cache hits, blocks, and publication.
- Operational boundary: This is public-page retrieval, not authorization to bypass login, CAPTCHA, or access controls. The crawler uses one sequential browser worker, per-source delay, cache, and a persistent profile. It does not rotate identities or proxies. If the retailer blocks the browser, the run reports `blocked` and preserves the last good data; `--headed` exists only to complete a normal interactive browser challenge.

## 2026-09-01 - Brand Discovery Is a Core Feedback Loop

- Context: Requiring a person to paste a store URL assumes they already know the brand, while the product problem is that good menswear labels are difficult to find. Hard-coded sources also mix the global crawl contract with one person's preferences.
- Decision: Shopbot automatically mines trusted multi-brand retailer catalogues for previously unknown vendors, filters products to menswear, scores candidates against taste terms, and presents up to three representative products with provenance. The current `data/brand-candidates.json` artifact is profile-scoped because it includes taste-derived scores, learned signals, and explanations; follow, occasional, reject, and too-expensive decisions remain in the current profile's taste data. The local server refreshes discovery at startup and every six hours without overlapping runs.
- Why: Stockists encode useful brand adjacency. A future multi-user product must split raw shared discovery evidence from profile-private scoring before serving this data across accounts.
- Consequences: Manual URL entry is optional rather than the primary flow. A partial retailer outage preserves prior candidates; a total fetch failure does not overwrite the last good registry. Following a brand is persisted and recoverable, but direct brand-site resolution and account authentication remain later productization work.
- Confidence boundary: Until enough product and brand decisions exist, stockist adjacency plus matching product terms is labeled `exploratory`, not personalized proof. The initial retailer set is denim-heavy and its output must not be presented as a balanced view of the user's full taste.
- Learning behavior: Follow, occasional, and reject decisions reinforce or suppress the candidate's matched style signals on later discovery runs. `Too expensive` does not count as a style rejection; price learning remains separate.

## 2026-09-01 - Enforce Menswear at Ingestion

- Context: Several general Shopify feeds mix men's and women's products. Ten women's products from Edwin, Marine Layer, Outerknown, and A.P.C. entered the catalogue because the scout checked only the display title; several titles omitted any gender marker even though merchant metadata identified the women's line.
- Decision: Keep the catalogue menswear-focused. The scout filters the combined title, handle, product type, tags, and vendor metadata, with exact source-level handle exclusions for ambiguous exceptions. It does not infer a model's gender from a photograph.
- Why: Merchant product metadata is a more reliable and respectful product boundary than guessing from a person's appearance, and source-specific exclusions cover incomplete metadata without weakening the global filter.
- Consequences: The ten known mismatches were removed. New Shopify leads must pass the full-product filter before an image is cached or a suggestion is published.

## 2026-09-01 - Separate Discovery Age from Purchase Verification

- Context: Applying the seven-day verification timeout to collection-level leads made the whole catalogue render as `stale`, even though those records never claimed purchase-ready price or stock. Votes also lacked downstream actions, catalogue modes were nearly universal, and post-purchase evidence had nowhere to live.
- Decision: A `lead` remains a discovery lead at any age and always says its price is not purchase-ready. Only retailer-page `verified` evidence expires after seven days. A `+2` vote enters the derived verification queue; personalized sorting activates after 15 suggestion votes; purchase outcomes persist in `taste/outcomes.json` and outweigh ordinary votes. The Shopify scout now assigns narrower title/product-derived categories and modes, with a reproducible normalization command for its own records.
- Why: Discovery usefulness, purchase safety, preference learning, and ownership outcomes are different signals. Collapsing them into one badge or one vote obscures the workflow and teaches the ranker from weaker evidence than actual ownership.
- Consequences: The dashboard exposes `Lead`, `Verified`, `Expired verification`, and `Needs verification` separately. `For you` falls back to newest until the threshold is met. Curated records keep their authored modes; normalization rewrites only scout-produced taxonomy plus the legacy `accessory` spelling.

## 2026-09-01 - Suggestions Open as an Unvoted Review Queue

- Context: Saving a suggestion vote updated `taste/votes.json`, but the default `Any vote` filter left the card in place and made the action look ineffective.
- Decision: Default and reset the Suggestions vote filter to `To review` (`unvoted`). A completed vote removes the card from the active queue; `Any vote`, `Liked`, and `Disliked` keep every result recoverable.
- Why: The primary dashboard job is processing a large candidate queue. Immediate removal is clear feedback without deleting the underlying suggestion or taste signal.
- Consequences: Shared URLs omit the default `unvoted` filter and encode only non-default filter choices. Vote-filter tests must cover queue removal and recovery.

## 2026-08-17 - A Blocked Brand Site Is Not a Dropped Brand

- Context: Kale pushed back on treating "HTML collection pages don't render" as a reason to drop stores. That reading would exclude Uniqlo, Levi's, Nike, AE, Gap, Nordstrom — most of the useful mass market.
- Decision: Three fetch methods, in order: (1) Shopify `products.json`, (2) stocking-retailer JSON (ShopWSS), (3) WebSearch then a readable PDP (Zappos works; Nordstrom currently empty). A 403/timeout on the brand homepage stays on the roster as `blocked-brand-reachable-via-retailer`. Never remove Levi/Uniqlo/Nike from scope because their own site bot-blocks.
- Why: The board's #1 garment is baggy light-wash jeans. That lives at Levi/Uniqlo/AE more than at Carhartt. Losing those brands because of HTML emptiness is a fetch-method failure, not a taste decision.
- Consequences: `config/sources.json` documents `fetchMethods`. Levi 568 was published from a Zappos PDP at $110 after levi.com 403'd. Uniqlo still has no working path; keep probing, don't skip.

## 2026-08-15 - Reproducible Watcher Registration, Seven-Day Display Staleness, and Exact-Bind Diagnostics

> Freshness portion superseded on 2026-09-01: the seven-day timeout now applies only to retailer-page verification, not discovery leads.

- Context: The watcher task had disappeared, old suggestion records still displayed their stored status as fresh, and a generic localhost probe could hit a different listener while hiding which process blocked the dashboard's actual bind.
- Decision: Keep `engine/register-price-watch.ps1` as the ASCII-only, PowerShell 5.1-compatible task definition for the two daily triggers, pointing directly to `engine/price-watch.ps1` through `powershell.exe -File` without a content-log wrapper or embedded watch config. In the dashboard, derive an effective `stale` status when `checkedAt` is missing or more than seven days old while preserving stored JSON. On listen failure, diagnose the exact configured host and port and report its owning process; production remains bound to `127.0.0.1`.
- Why: Scheduled state must be reproducible without reintroducing shared log ownership, verification labels must decay with their evidence, and address-specific diagnostics prevent Tailscale listeners on other local addresses from masquerading as dashboard health.
- Consequences: Restore the watcher by running the registration script but never start a live shopping run as a registration test. The status chip, detail line, and Verification filter must all use the same effective status. Dashboard availability checks and bind failures must name `127.0.0.1:7877`, not generic `localhost` or all interfaces.

## 2026-07-13 - Separate Wrapper and Content Log Ownership

- Context: Scheduled watcher runs repeatedly left their header log open, so the content producer could not atomically replace or append the same file on Windows.
- Decision: The wrapper may write and close its own execution log, but must not pre-create or hold the content report target. Content publication uses a separately owned path and atomic promotion.
- Why: Windows file sharing is explicit; two writers cannot safely assume they can replace the same open file.
- Consequences: Watcher diagnostics and generated shopping content remain distinct and neither process needs to work around `EPERM` with ad hoc sibling filenames.

## 2026-08-06 - Five-Level Taste Voting and Known-ID Validation

- Context: The dashboard needed a more expressive taste signal for both Pinterest references and retail candidates, while its vote endpoint could previously accept arbitrary keys and write them directly into the primary taste signal.
- Decision: Use the five-level scale `-2`, `-1`, `0`, `1`, `2`, where zero deletes the stored signal, and accept votes only for a currently known corpus or suggestion ID. Normalize legacy and out-of-range stored values on read, serialize writes, and publish `taste/votes.json` through a sibling temporary file followed by rename.
- Why: The extra resolution distinguishes strong preferences, and known-ID validation prevents junk keys from accumulating. Tolerant reads preserve service availability while serialized atomic publication prevents fast clicks from losing or truncating the taste signal.
- Consequences: The dashboard must obtain the scale from `/api/state`, clients cannot create votes for unseen candidates, and a malformed or concurrently changed source file degrades to a safe empty/normalized state instead of crashing the API.

## 2026-08-06 - Suggestion Records Carry Their Own Evidence

- Context: `data/suggestions.json` previously held only a title, price, and one-line verdict, so a candidate's price could not be distinguished from a stale tracker figure once it was on screen.
- Decision: Schema v2 requires every suggestion to carry `matchReasons`, a `provenance` block naming the source type and the evidence actually observed, and a `verification` block with `status`, `checkedAt`, the observed price, and stock. The dashboard renders verification age next to the price and labels anything not verified as an unverified lead.
- Why: `AGENTS.md` treats retailer and tracker data as leads until the retailer page is verified. That rule only holds if the evidence travels with the record instead of living in a chat transcript.
- Consequences: A producer cannot publish a bare price. Records whose retailer page could not be read directly must say so in `provenance.foundVia`, and per-length or "from" pricing must be described in `evidence` rather than presented as a confirmed price.

## 2026-08-07 - Volume Over Intake; Leads Are Publishable, Silently Unverified Prices Are Not

- Context: The profile carries 14 `TODO` fields and the obvious next step looked like a sizing and lifestyle interview. Asked for it, Kale declined: fit is not one number, it depends on the fit he is going for, and he would rather browse many options than answer questions.
- Decision: Stop treating the profile as the thing to complete. Generate volume, let votes carry the taste signal, and keep the profile as the fallback it was always designed to be. To make volume affordable, candidates may be published from a brand collection listing as `verification.status: "lead"` with the price range in `evidence` — and are promoted to `verified` only when a vote justifies opening the product page.
- Why: The repo already holds that votes outrank profile prose. An interview optimizes the fallback while the primary signal sits empty. Publishing leads is consistent with `AGENTS.md` — retailer data is a lead until the retailer page is verified — provided the label is visible on the card rather than buried.
- Consequences: Most of the catalogue will be unverified at any time, so the card must show the verified/lead distinction at a glance, and any recommendation to actually buy requires promoting that record first. Suggestion cards optimize for scanning, not auditing: evidence moves behind a disclosure. The `TODO`s stay `TODO` deliberately; only base top size and jean waist are worth asking for, because they decide whether an item is orderable at all.

## 2026-08-06 - Two Independent Health Checks

- Context: Renaming the single `test` script to add dashboard coverage would have broken the hash-pinned Control Tower contract, and folding both suites behind one check id would have made a dashboard failure look like a watcher failure.
- Decision: `npm test` runs `test:watcher && test:dashboard`, and the contract pins each sub-script as its own required check (`watcher-regression`, `dashboard-regression`). The watcher script body was copied byte-for-byte so its pinned `script_sha256` is unchanged; `dashboard` was added to `input_paths`.
- Why: Separate ids attribute a failure to the right layer, and an unchanged watcher hash proves the regression itself was not altered while adding coverage around it.
- Consequences: Adding a suite means adding a check and its script hash, not editing an existing one. `data/` is deliberately excluded from `input_paths` so routine suggestion publishing does not invalidate cached health evidence.
