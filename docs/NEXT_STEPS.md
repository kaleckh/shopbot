# Next Steps

## Now

- Re-register the `ClaudePriceWatch` scheduled task from `engine/price-watch.ps1`. Verified 2026-08-06: `Get-ScheduledTask ClaudePriceWatch` returns nothing and the newest file in `logs/` is `watch-2026-07-19_162302`, so the watcher has been silent for roughly 18 days. This is part of a machine-wide loss of user-created scheduled tasks. Nothing below that depends on "the next scheduled run" can happen until it is restored.
- Observe the next scheduled watcher run and confirm the normal final report is published without an `EPERM` companion-file workaround.
- Vote through the first v2 batch on the Suggestions tab. Eight shoe/accessory candidates were published 2026-08-06 with live retailer evidence; votes are the signal that makes the next scout pass better than the profile prior.
- When making dashboard changes, run `npm run test:dashboard` and the hash-pinned watcher regression through `npm test`.

## Later

- Continue the taste-profile intake and fashion watch iteration described in `README.md`.
- Review the shared-link behavior for suggestion filters and the five-level signal during normal personal use at mobile width.

## Risks / Unknowns

- The isolated ownership/config-path regression passes; the next real scheduled run is still the final environment-level confirmation and must not initiate a purchase.
- The v2 suggestion batch was verified by direct agent page-reads, not by a watcher run. Prices and stock decay quickly; treat any record whose `verification.checkedAt` is more than a few days old as stale regardless of its stored status.
- nike.com, newbalance.com, converse.com, and END all refused automated reads (HTTP 403/416) during the 2026-08-06 pass. Candidates for those brands are priced from a stocking retailer instead, which is recorded per record in `provenance.foundVia`.
- `tower health shopbot --run` currently exits before reaching shopbot because global registry validation fails on an unrelated `project:unreal-copilot` contract. Shopbot's own contract validates clean and both checks pass when evaluated directly.
