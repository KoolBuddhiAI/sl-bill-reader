# Tasks: Multilingual Bill Reader → MYOB Vouchers (Iteration 1)

**Change:** bill-reader-myob-vouchers
**Created:** 2026-10-14
**Total Tasks:** 11

## Summary

Build a local FastAPI app in four waves:
1. Foundation and reference data.
2. Pipeline components and the MYOB export, built in parallel.
3. Orchestration, review UI and the Surya fallback.
4. Evaluation on the five supplied samples, plus docs.

All tests run offline using recorded LLM fixtures. Live accuracy is compared across model profiles (GLM, DeepSeek; OpenAI/Claude when keys are added) with `bill-reader eval --models …`.

## Tasks

### Wave 1 — Foundation, reference data, model layer (T1b after T1)

- [x] `T1` — Project scaffold, config, database models
  - Files: `pyproject.toml`, `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, `bill_reader/{__init__,config,db,models,schemas,app,cli}.py`, `tests/conftest.py`
  - Estimate: medium
  - Notes: Settings per design (thresholds, paths, home currency LKR, default bank `1-1110`). SQLModel tables from design's Data Model; Decimal stored as TEXT. Pydantic `BillExtraction` schema (FR-7/8) — also the tool/JSON schema sent to the model. App factory creates DB on startup. `bill-reader serve` CLI. Set `build.test_command: pytest` in `.specclaw/config.yaml`.

- [~] `T2` — Sample ground truth, chart of accounts, tax codes, MYOB import formats
  - Files: `samples/ground_truth/0{1..5}-*.json`, `config/chart_of_accounts.sample.csv`, `config/tax_codes.yaml`, `config/myob_import_formats.yaml`
  - Estimate: small
  - Notes: Ground truth values from spec's Sample Set table (incl. expected account code). Sample SL SME chart: ~40 accounts in MYOB format (`1-1110 Cash at Bank`, `5-1000 Purchases`, `6-xxxx` Motor Vehicle Repairs, Repairs & Maintenance, Meals & Entertainment, Staff Welfare, Office Supplies, Utilities, Rent, Travel, etc.). Import formats: Spend Money and Service Purchases column lists per AccountRight import layout (A1). Check against MYOB's import/export field reference and comment any uncertain columns.

- [ ] `T11` — LLM provider layer & model profiles
  - Files: `bill_reader/llm/{__init__,profiles,base,openai_compat,anthropic_client}.py`, `config/models.yaml`, `.env.example` (`ZAI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`), `bill_reader/cli.py` (`models list`, `models check`), `tests/test_llm_*.py`
  - Estimate: medium
  - Depends: T1
  - Notes:
    - FR-10, FR-10a, FR-10c.
    - Profile fields: `provider`, `base_url`, `model`, `api_key_env`, `supports_vision`, `supports_tools`, `supports_json_mode`, `max_image_px`, `timeout_s`, `price_in_per_m`, `price_out_per_m`.
    - Initial profiles:
      - `glm-vision` (Z.ai `https://api.z.ai/api/paas/v4`, `glm-4.6v` or the newest GLM-V);
      - `glm-vision-flash`;
      - `deepseek-vision` (`deepseek-flash`, image input since Aug–Sep 2026);
      - `deepseek-text` (`deepseek-chat`, text-only);
      - `openai-vision` and `claude-vision`, disabled until a key is set.
    - **Check model ids, base URLs and capabilities against current provider docs while building.** Correct the YAML with what you find.
    - `complete_structured()` picks its strategy as tools, then JSON mode, then prompt JSON. It always validates with Pydantic, makes one repair retry, and returns usage and latency.
    - `models check` probes each profile that has a key: a tiny text call, plus an image call for vision profiles. It reports results without printing keys.
    - Tests use a fake HTTP transport.

### Wave 2 — Pipeline components (parallel)

- [ ] `T3` — Ingestion, watched folder, pre-processing
  - Files: `bill_reader/{ingest,watcher,preprocess}.py`, `tests/test_ingest.py`, `tests/test_preprocess.py`
  - Estimate: medium
  - Depends: T1
  - Notes: FR-1–FR-6. SHA-256 dedupe. Allowed types. Store originals under `data/documents/<sha>/`. pypdfium2 at 200 DPI, EXIF transpose, resize long edge to 2000 px, pillow-heif. Inbox watcher waits until size has been stable for 2 s, then moves the file to `processed/` or `failed/`. Ingest takes an `enqueue` callback so it stays decoupled from the worker.

- [ ] `T4` — Vision & OCR+text extractors, fallback chain, validation & confidence
  - Files: `bill_reader/extract/{base,vision,ocr_text,prompts,orchestrator}.py`, `bill_reader/validate.py`, `tests/test_extract.py`, `tests/test_validate.py`, `tests/fixtures/llm/<profile>/*.json`
  - Estimate: large
  - Depends: T1, T11
  - Notes:
    - FR-7–FR-12, FR-10b. Model-agnostic: the extractors take a `ModelProfile` and call `LLMClient`. The orchestrator walks `fallback_chain` and records profile, model, mode, latency and tokens on the bill.
    - The prompt covers the LK/IN context and pitfalls: cash tendered/change/"you saved" are not the total; list vs discounted columns; lakh grouping; dd/mm dates; original script plus English translation; approximate normalised boxes; per-field confidence; `not_a_bill`; multi-document warning.
    - `OcrTextLLMExtractor` takes OCR lines from an injected `OcrEngine` (Surya implementation in T9; a fake in tests). It is unavailable when there is no OCR engine.
    - An exhausted chain marks the bill `failed` with a reason per profile.
    - Validation applies the FR-12 rules and confidence factors.
    - Record fixtures per profile by running once against the samples (gated by `RECORD_FIXTURES=1` and the available keys: GLM and DeepSeek). Tests replay them.

- [ ] `T5` — Categoriser
  - Files: `bill_reader/categorise.py`, `tests/test_categorise.py`, `tests/fixtures/llm/<profile>/categorise_*.json`
  - Estimate: medium
  - Depends: T1, T11, T2
  - Notes:
    - FR-13–FR-15. Load and replace the chart from CSV, keeping detail expense/COGS/asset accounts only.
    - Supplier-name normaliser: lowercase, strip `(pvt) ltd`, punctuation and whitespace; prefer the English name.
    - Supplier history hit gives confidence 0.95. Otherwise a structured call to the **categorisation profile** (a text-only model is fine; default `deepseek-text`); if the returned code is not in the chart, retry once, then pick `6-9999 Suspense/Uncategorised` at confidence 0.
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
    - `/api/models` and `PUT /api/models/active` (FR-10d); `reextract?profile=`.
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
      - Settings page: import chart of accounts; a model profiles table (key present, vision probe, last check) with selectors for the extraction and categorisation profiles; Surya availability.
      - Review page also shows "Extracted by <profile> (<model>, <mode>, <latency>)" and a "Re-extract with…" dropdown.
    - Fonts: Noto Sans Sinhala and Noto Sans Tamil from Google Fonts.
    - Smoke test with Playwright (Chromium is pre-installed): upload sample 02, approve, export.

- [ ] `T9` — Surya-OCR engine & heuristic last-resort extractor
  - Files: `bill_reader/ocr/{__init__,surya}.py`, `bill_reader/extract/heuristic.py`, `pyproject.toml` (`[surya]` extra), `tests/test_ocr_surya.py`
  - Estimate: medium
  - Depends: T4
  - Notes:
    - FR-11 and NFR-2. Lazy import; `is_available()`. Run detection and recognition with langs `si`, `ta`, `en`.
    - Implements the `OcrEngine` used by `OcrTextLLMExtractor` (this enables text-only models such as DeepSeek text, AC-16). `HeuristicExtractor` is the last resort when no LLM is reachable: the largest amount near "total" / "එකතුව" / "மொத்தம்", the first date-looking token, and the first non-empty line as supplier, all at confidence ≤ 0.4.
    - Snap field boxes to the best-matching OCR line.
    - Tests mock Surya output. An `is_available()=False` path must exist.

### Wave 4 — Evaluation & demo

- [ ] `T10` — Multi-model eval & comparison, README, demo run
  - Files: `bill_reader/evaluate.py`, `bill_reader/cli.py` (`eval`, `import-accounts`), `README.md`, `docs/eval-results.md`
  - Estimate: medium
  - Depends: T7, T8, T9
  - Notes:
    - FR-24, AC-15: `bill-reader eval samples/ --models glm-vision,glm-vision-flash,deepseek-vision,deepseek-text` runs the pipeline in-process on `samples/` once per profile. Profiles without a key are skipped and reported. Compare against ground truth with: normalised string match for supplier and bill number, exact date, |Δ| ≤ 1.00 for totals, exact currency and account code.
    - Output a side-by-side table: profile × field accuracy, per-sample totals read, mean latency, tokens and estimated cost. Write markdown plus JSON.
    - Run live with the **GLM and DeepSeek** keys on the five samples (AC-4, AC-5, AC-8). Record results honestly, misses included, and recommend the default profile.
    - README: setup (`.env`, docker compose / uvicorn, optional Surya), demo walkthrough, how to add or switch a model profile (e.g. adding an OpenAI key), how to import the generated files into MYOB AccountRight (AC-12 steps), the assumptions A1–A9 to confirm with the client, and the iteration-2 roadmap.

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
