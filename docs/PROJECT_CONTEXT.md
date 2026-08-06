# Project Context

## Summary

Shopbot is Kale's personal fashion and shopping agent. Its live watcher verifies configured retailer pages for price and stock conditions, while taste-driven scouting and a future conversational agent build on the same JSON configuration.

## Stack and Repository Map

- Windows PowerShell 5.1 watcher: `engine/price-watch.ps1`
- Watch and profile configuration: `config/`
- Taste corpus and votes: `taste/`
- Local dashboard: `dashboard/` (two-tab taste and suggestions review surface with client-side filters)
- Runtime data and logs: `data/`, `logs/`
- Verification: `npm test` (`test:watcher` + `test:dashboard`); Control Tower owns the hash-pinned `watcher-regression` and `dashboard-regression` health checks.

## Constraints

- PowerShell scripts are ASCII-only for Windows PowerShell 5.1 compatibility.
- A deal alert is actionable only after retailer-page verification.
- Scheduled runs must not hold the content log open while another process writes or replaces it.
- The watcher validates `config/watches.json` locally and passes only its exact path to the producer, preventing command-line prompt truncation as the watch list grows.
- Testing must avoid false alerts and unintended purchases.
- Dashboard data is dependency-free browser HTML/JS served by the local Node server; suggestions remain leads until retailer-page verification is present.

## Current Priority

Keep the scheduled watcher reliable while using the dashboard as the review surface for taste references and verified retail candidates. Reports use private capture and atomic publication so the final path is never open during producer execution; confirm that behavior on the next scheduled run.
