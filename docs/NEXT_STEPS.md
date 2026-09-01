# Next Steps

## Now

- Vote the Suggestions tab. Catalogue is ~200 leads across ~60 brands. Votes will tell us which of the new mills/streetwear names to keep mining.
- Next source work: more Zappos/ShopWSS PDPs for Uniqlo/AE/Gap baggy denim (brand sites still fail); paginate Okayama/Blue Owl; fix Norse DKK-as-USD before republishing.
- `ClaudePriceWatch` ran both 2026-08-16 slots (NOALERT, KLEVV $225). Next run is the regular 9:23 / 16:23 cadence; do not start it manually just to test.
- **Do not run a profile intake interview.** Kale declined it 2026-08-07 and gave the reason: fit is not one number, it depends on the fit he is going for (which the mode-based schema already says), and he would rather see lots of options to react to than fill in a profile. The 14 `TODO`s stay `TODO` on purpose — votes are the primary signal and the profile is the fallback. The only outstanding facts worth asking for opportunistically are **base top size and jean waist**, because those decide whether a suggestion is even orderable.
- Verify the 18 `lead` records on vote. They were priced from brand collection grids, not product pages; when Kale votes one up, open the product page and promote it to `verified` with real per-size stock.
- When making dashboard changes, run `npm run test:dashboard` and the hash-pinned watcher regression through `npm test`.

## Later

- Add at least one fashion watch. `config/watches.json` still holds only the 2TB NVMe entry, so the watcher layer contributes nothing to the fashion side of the tool.
- Review the shared-link behavior for suggestion filters and the five-level signal during normal personal use at mobile width.
- Re-shoot the Converse product image if a full-size black/egret photo becomes reachable; the cached one is a correct but 78px swatch (see that record's `imageNote`).

## Risks / Unknowns

- The isolated ownership/config-path regression passes; the next real scheduled run is still the final environment-level confirmation and must not initiate a purchase.
- The v2 suggestion batch was verified by direct agent page-reads, not by a watcher run. Prices and stock decay quickly; the dashboard now treats a missing or more-than-seven-day-old `verification.checkedAt` as stale regardless of stored status, without rewriting the record.
- nike.com, newbalance.com, converse.com, and END all refused automated reads (HTTP 403/416) during the 2026-08-06 pass. Candidates for those brands are priced from a stocking retailer instead, which is recorded per record in `provenance.foundVia`. Added 2026-08-07: **levi.com** now 403s with `Retry-After: 10800`, and uniqlo.com times out repeatedly. Brand collection pages are a far cheaper source than product pages when they work — three fetches produced 18 products and their photos.
- Knits and light-wash denim are still missing from the batch entirely, despite being the #1 and #4 recurring garments on the board. Every source tried for them failed; they were left out rather than guessed.
- `tower health shopbot --run` currently exits before reaching shopbot because global registry validation fails on an unrelated `project:unreal-copilot` contract. Shopbot's own contract validates clean and both checks pass when evaluated directly.
- The taste prior is now built on all 50 retrievable pins, but the board has 111 pins total. The other 61 need authentication to fetch, so the profile is still a sample, not the whole board.
