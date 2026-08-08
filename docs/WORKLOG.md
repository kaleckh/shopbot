# Worklog

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
