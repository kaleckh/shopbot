# Shopbot Agent Guide

Read `README.md`, `docs/PROJECT_CONTEXT.md`, `docs/DECISIONS.md`, and `docs/NEXT_STEPS.md` before changes.

## Working Rules

- Keep `engine/*.ps1` compatible with Windows PowerShell 5.1 and ASCII-only.
- Treat retailer and tracker data as leads until the watcher verifies the retailer page.
- Deal alerts must remain rare, verified, and bounded by `config/watches.json`.
- The scheduled wrapper and the content producer must use separate log ownership. Never keep the content target open while another process is expected to replace or append it.
- Preserve taste/profile and watch configuration unless the user asks to change them.
- Run parser and focused behavioral checks after watcher changes; do not trigger a real shopping run merely to test file ownership.

After meaningful work, update the repo memory files under `docs/`.
