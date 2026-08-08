# Decisions

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
