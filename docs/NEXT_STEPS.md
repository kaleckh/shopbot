# Next Steps

## Now

- Re-register the `ClaudePriceWatch` scheduled task from `engine/price-watch.ps1`. Verified 2026-08-06: `Get-ScheduledTask ClaudePriceWatch` returns nothing and the newest file in `logs/` is `watch-2026-07-19_162302`, so the watcher has been silent for roughly 18 days. This is part of a machine-wide loss of user-created scheduled tasks. Nothing below that depends on "the next scheduled run" can happen until it is restored.
- Observe the next scheduled watcher run and confirm the normal final report is published without an `EPERM` companion-file workaround.
- Vote through the first v2 batch on the Suggestions tab. Eight shoe/accessory candidates, now with cached product photos, are waiting; votes are the signal that makes the next scout pass better than the profile prior.
- **Do not run a profile intake interview.** Kale declined it 2026-08-07 and gave the reason: fit is not one number, it depends on the fit he is going for (which the mode-based schema already says), and he would rather see lots of options to react to than fill in a profile. The 14 `TODO`s stay `TODO` on purpose — votes are the primary signal and the profile is the fallback. The only outstanding facts worth asking for opportunistically are **base top size and jean waist**, because those decide whether a suggestion is even orderable.
- Verify the 18 `lead` records on vote. They were priced from brand collection grids, not product pages; when Kale votes one up, open the product page and promote it to `verified` with real per-size stock.
- When making dashboard changes, run `npm run test:dashboard` and the hash-pinned watcher regression through `npm test`.

## Later

- Add at least one fashion watch. `config/watches.json` still holds only the 2TB NVMe entry, so the watcher layer contributes nothing to the fashion side of the tool.
- Review the shared-link behavior for suggestion filters and the five-level signal during normal personal use at mobile width.
- Re-shoot the Converse product image if a full-size black/egret photo becomes reachable; the cached one is a correct but 78px swatch (see that record's `imageNote`).

## Risks / Unknowns

- The isolated ownership/config-path regression passes; the next real scheduled run is still the final environment-level confirmation and must not initiate a purchase.
- The v2 suggestion batch was verified by direct agent page-reads, not by a watcher run. Prices and stock decay quickly; treat any record whose `verification.checkedAt` is more than a few days old as stale regardless of its stored status.
- nike.com, newbalance.com, converse.com, and END all refused automated reads (HTTP 403/416) during the 2026-08-06 pass. Candidates for those brands are priced from a stocking retailer instead, which is recorded per record in `provenance.foundVia`. Added 2026-08-07: **levi.com** now 403s with `Retry-After: 10800`, and uniqlo.com times out repeatedly. Brand collection pages are a far cheaper source than product pages when they work — three fetches produced 18 products and their photos.
- Knits and light-wash denim are still missing from the batch entirely, despite being the #1 and #4 recurring garments on the board. Every source tried for them failed; they were left out rather than guessed.
- `tower health shopbot --run` currently exits before reaching shopbot because global registry validation fails on an unrelated `project:unreal-copilot` contract. Shopbot's own contract validates clean and both checks pass when evaluated directly.
- The taste prior is now built on all 50 retrievable pins, but the board has 111 pins total. The other 61 need authentication to fetch, so the profile is still a sample, not the whole board.
