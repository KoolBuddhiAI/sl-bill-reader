# Tasks: Multilingual Bill Reader → MYOB Vouchers (Iteration 1)

**Change:** bill-reader-myob-vouchers
**Created:** 2026-10-14
**Total Tasks:** 10

## Summary

Build a local FastAPI app in four waves:
1. Foundation and reference data.
2. Pipeline components and the MYOB export, built in parallel.
3. Orchestration, review UI and the Surya fallback.
4. Evaluation on the five supplied samples, plus docs.

All tests run offline using recorded Claude fixtures. Live accuracy is measured with `bill-reader eval`.

## Tasks

### Wave 1 — Foundation & reference data

- [ ] `T1` — Project scaffold, config, database models
  - Files: `pyproject.toml`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `bill_reader/{__init__,config,db,models,schemas,app,cli}.py`, `tests/conftest.py`
  - Estimate: medium
  - Notes: Settings per design (API key, `BILL_READER_MODEL` default `claude-opus-5-5`, thresholds, paths, home currency LKR, default bank `1-1110`). SQLModel tables from design's Data Model; Decimal stored as TEXT. Pydantic `BillExtraction` schema (FR-7/8) — this is also the tool schema sent to Claude. App factory creates DB on startup. `bill-reader serve` CLI. Set `build.test_command: pytest` in `.specclaw/config.yaml`.

- [ ] `T2` — Sample ground truth, chart of accounts, tax codes, MYOB import formats
  - Files: `samples/ground_truth/0{1..5}-*.json`, `config/chart_of_accounts.sample.csv`, `config/tax_codes.yaml`, `config/myob_import_formats.yaml`
  - Estimate: small
  - Notes: Ground truth values from spec's Sample Set table (incl. expected account code). Sample SL SME chart: ~40 accounts in MYOB format (`1-1110 Cash at Bank`, `5-1000 Purchases`, `6-xxxx` Motor Vehicle Repairs, Repairs & Maintenance, Meals & Entertainment, Staff Welfare, Office Supplies, Utilities, Rent, Travel, etc.). Import formats: Spend Money and Service Purchases column lists per AccountRight import layout (A1). Check against MYOB's import/export field reference and comment any uncertain columns.

### Wave 2 — Pipeline components (parallel)

- [ ] `T3` — Ingestion, watched folder, pre-processing
  - Files: `bill_reader/{ingest,watcher,preprocess}.py`, `tests/test_ingest.py`, `tests/test_preprocess.py`
  - Estimate: medium
  - Depends: T1
  - Notes: FR-1–FR-6. SHA-256 dedupe. Allowed types. Store originals under `data/documents/<sha>/`. pypdfium2 at 200 DPI, EXIF transpose, resize long edge to 2000 px, pillow-heif. Inbox watcher waits until size has been stable for 2 s, then moves the file to `processed/` or `failed/`. Ingest takes an `enqueue` callback so it stays decoupled from the worker.

- [ ] `T4` — Claude extractor, orchestrator, validation & confidence
  - Files: `bill_reader/extract/{base,claude,prompts,orchestrator}.py`, `bill_reader/validate.py`, `tests/test_extract_claude.py`, `tests/test_validate.py`, `tests/fixtures/claude/*.json`
  - Estimate: large
  - Depends: T1
  - Notes:
    - FR-7–FR-12. Forced tool use with the `BillExtraction` schema; one retry with the validation error.
    - The prompt covers the LK/IN context and pitfalls: cash tendered/change/"you saved" are not the total; list vs discounted columns; lakh grouping; dd/mm dates; original script plus English translation; approximate normalised boxes; per-field confidence; `not_a_bill`; multi-document warning.
    - The orchestrator calls the fallback via the `Extractor` protocol. A `None` fallback means `failed` with a reason.
    - Validation applies the FR-12 rules and confidence factors.
    - Record fixtures by running once against the samples (gated by an env var); tests replay them.

- [ ] `T5` — Categoriser
  - Files: `bill_reader/categorise.py`, `tests/test_categorise.py`, `tests/fixtures/claude/categorise_*.json`
  - Estimate: medium
  - Depends: T1, T2
  - Notes:
    - FR-13–FR-15. Load and replace the chart from CSV, keeping detail expense/COGS/asset accounts only.
    - Supplier-name normaliser: lowercase, strip `(pvt) ltd`, punctuation and whitespace; prefer the English name.
    - Supplier history hit gives confidence 0.95. Otherwise a Claude forced-tool classification; if the returned code is not in the chart, retry once, then pick `6-9999 Suspense/Uncategorised` at confidence 0.
    - Tax code rule: `VAT` when vat_amount > 0, else `N-T`.

- [ ] `T6` — MYOB import file export
  - Files: `bill_reader/export/{base,myob_file}.py`, `tests/test_export_myob.py`, `tests/fixtures/export/*.txt`
  - Estimate: medium
  - Depends: T1, T2
  - Notes:
    - FR-21–FR-23. `VoucherSink` protocol. A YAML-driven column writer.
    - Output is tab-delimited and CRLF. Amounts are Decimal with 2 dp and no thousands separators. Dates are formatted per config (`dd/mm/yyyy`).
    - Foreign currency: amount = total × rate, and the memo appends `Orig INR 7,226.00 @ 0.28`.
    - Amounts: Spend Money gets the tax-inclusive amount plus the VAT amount; SSCL goes into the expense amount (A5).
    - Write one file per voucher type, zipped together when both exist. Mark bills `exported` with the batch id; re-download by batch.
    - Golden-file tests.

### Wave 3 — Orchestration, UI, fallback

- [ ] `T7` — Worker pipeline & JSON API
  - Files: `bill_reader/{worker,api}.py`, `bill_reader/app.py` (wire startup), `tests/test_api.py`, `tests/test_worker.py`
  - Estimate: medium
  - Depends: T3, T4, T5, T6
  - Notes:
    - Thread-pool worker runs: preprocess → extract → validate → categorise → persist fields, line items and audit, then sets status `needs_review` or `failed`. On restart, bills left in `processing` are re-queued.
    - All endpoints in design's API table.
    - PATCH records `corrected` audit events (original vs new).
    - Approve checks:
      - required fields (supplier, date, total, account code);
      - an exchange rate when currency ≠ home currency;
      - every red or amber required field was confirmed.
    - Approve then updates SupplierHistory.
    - Export endpoint calls `MyobFileSink`.
    - API tests use a fake extractor.

- [ ] `T8` — Review UI
  - Files: `bill_reader/web.py`, `bill_reader/templates/{base,bills_list,bill_review,export,settings}.html`, `bill_reader/static/{review.js,app.css}`
  - Estimate: large
  - Depends: T7
  - Notes:
    - FR-16–FR-20.
      - List page: thumbnails, status filter, auto-refresh while any bill is processing; drag-and-drop upload.
      - Review page: zoom/pan image with page tabs and a SVG overlay that draws the bbox on focus/hover; confidence colours; warnings banner; editable line items; searchable account picker using `/api/accounts?q=` and showing the suggestion reason; tax code select; Spend Money/Purchase toggle; paying account; an exchange-rate field when currency ≠ LKR; Approve, Re-extract and Delete buttons; audit log panel.
      - Export page: approved count, Export button, batch history.
      - Settings page: import chart of accounts, show active model and whether Surya is available.
    - Fonts: Noto Sans Sinhala and Noto Sans Tamil from Google Fonts.
    - Smoke test with Playwright (Chromium is pre-installed): upload sample 02, approve, export.

- [ ] `T9` — Surya-OCR fallback extractor
  - Files: `bill_reader/extract/surya.py`, `pyproject.toml` (`[surya]` extra), `tests/test_extract_surya.py`
  - Estimate: medium
  - Depends: T4
  - Notes:
    - FR-11 and NFR-2. Lazy import; `is_available()`. Run detection and recognition with langs `si`, `ta`, `en`.
    - If Claude is reachable, re-extract with the OCR text attached (prompt variant from T4). Otherwise use a heuristic text-only extraction: the largest amount near "total" / "එකතුව" / "மொத்தம்", the first date-looking token, and the first non-empty line as supplier, all at confidence ≤ 0.4.
    - Snap field boxes to the best-matching OCR line.
    - Tests mock Surya output. An `is_available()=False` path must exist.

### Wave 4 — Evaluation & demo

- [ ] `T10` — Eval command, README, demo run
  - Files: `bill_reader/evaluate.py`, `bill_reader/cli.py` (`eval`, `import-accounts`), `README.md`, `docs/eval-results.md`
  - Estimate: medium
  - Depends: T7, T8, T9
  - Notes:
    - FR-24: run the pipeline in-process on `samples/`. Compare against ground truth with: normalised string match for supplier and bill number, exact date, |Δ| ≤ 1.00 for totals, exact currency and account code.
    - Print a table and write markdown. Run live on the five samples (AC-4, AC-5, AC-8) and record the results honestly, including misses.
    - README: setup (`.env`, docker compose / uvicorn, optional Surya), demo walkthrough, how to import the generated files into MYOB AccountRight (AC-12 steps), the assumptions A1–A9 to confirm with the client, and the iteration-2 roadmap.

---

## Legend

- `[ ]` Pending
- `[~]` In Progress
- `[x]` Complete
- `[!]` Failed

**Task format:**
```
- [ ] `T<n>` — <title>
  - Files: <files to create/modify>
  - Estimate: small | medium | large
  - Depends: <task ids> (if any)
  - Notes: <additional context>
```
