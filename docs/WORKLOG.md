# Worklog

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
