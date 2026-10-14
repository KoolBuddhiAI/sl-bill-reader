# Design: Multilingual Bill Reader → MYOB Vouchers (Iteration 1)

**Change:** bill-reader-myob-vouchers
**Created:** 2026-10-14

## Technical Approach

A single Python service, deliberately small:

- **FastAPI** serves both the JSON API and server-rendered pages (**Jinja2 + vanilla JS**). No separate SPA build. The review page needs one interactive piece, the image viewer with box overlays, which is about 150 lines of plain JS.
- **SQLite via SQLModel** for bills, field values, corrections, supplier history, export batches. Single user, local.
- **In-process background worker:** a `ThreadPoolExecutor` (2 workers) fed by an in-memory queue. On startup it re-queues bills stuck in `processing`. At ~50 bills/month, Celery or Redis would be overkill.
- **watchdog** observer thread for the inbox folder. It waits until the file size has been stable for 2 s before ingesting.
- **Extractor interface** with two implementations, plus an orchestrator implementing the FR-11 fallback rules:
  - `ClaudeExtractor`: Anthropic Messages API, image content blocks, and **forced tool use** with the `BillExtraction` JSON schema, so output is always schema-shaped. Default model `claude-opus-5-5`, chosen for best handwriting reading; set via `BILL_READER_MODEL`.
  - `SuryaExtractor`: optional import. Runs Surya OCR to get text lines + boxes. If Claude is reachable, it re-asks Claude with the OCR text attached. If not, it falls back to a text-only extraction (regex/heuristics for totals and dates; supplier = first line) at low confidence.
- **Bounding boxes:** Claude is asked for approximate normalised boxes. When Surya has run, each field box is snapped to the Surya line whose text best matches the value. Boxes are best-effort only (AC-7 requires just the total on sample 02).
- **Confidence:** `field_conf = model_conf × validation_factor`. Failed arithmetic checks multiply the fields involved by 0.6. Overall confidence = the minimum over the required fields (supplier, date, total).
- **Categoriser:** supplier history lookup first; otherwise one Claude call with a compact chart of accounts (code, name, type) plus supplier and line items. Forced tool output is `{account_code, confidence, reason}`, and the code is validated against the chart.
- **MYOB export:** a `VoucherSink` protocol with `MyobFileSink` (iteration 1). `MyobApiSink` comes in iteration 2. The file format is driven by `config/myob_import_formats.yaml`: an ordered column list per voucher type, each column mapped to a field path or constant. Output is tab-delimited, CRLF, one header row, with a blank line between records (MYOB's multi-line record convention).

## Architecture

```
            ┌──────────── web UI (Jinja + JS) ─────────────┐
 upload ───►│  /bills  /bills/{id}  /export  /settings     │
            └──────────────┬────────────────────────────────┘
                           │ FastAPI routes (app/api, app/web)
 inbox/ ──► watcher ──►  ingest.service ──► documents store (data/documents/<sha>/)
                           │  enqueue(bill_id)
                           ▼
                     worker (threads)
                           │
              preprocess ──► extract.orchestrator ──► validate ──► categorise
              (pdfium,       ├─ ClaudeExtractor                     ├─ supplier history
               Pillow)       └─ SuryaExtractor (optional)           └─ Claude classify
                           │
                           ▼
                     SQLite (bills, fields, corrections, suppliers, exports)
                           │
                review / approve ──► export.MyobFileSink ──► SpendMoney.txt / Purchases.txt (.zip)
                                    (iter 2: MyobApiSink)
```

## File Changes Map

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | create | Package `bill_reader`, deps, extras `[surya]`, `[dev]`, console script `bill-reader` |
| `.env.example`, `.gitignore`, `README.md` | create | Config template, ignore `data/`, `.env`, `inbox/`; run & demo instructions |
| `Dockerfile`, `docker-compose.yml` | create | One-container run; volumes for `data/`, `inbox/`, `config/` |
| `bill_reader/config.py` | create | Pydantic settings (API key, model, thresholds, paths, default bank account, home currency) |
| `bill_reader/db.py`, `bill_reader/models.py` | create | SQLModel engine/session; tables (see Data Model) |
| `bill_reader/schemas.py` | create | Pydantic `BillExtraction`, `FieldValue`, `LineItem`, `CategorySuggestion` |
| `bill_reader/ingest.py` | create | Save file, hash/dedupe, type check, create bill, enqueue |
| `bill_reader/watcher.py` | create | watchdog observer, stable-size wait, move to processed/failed |
| `bill_reader/preprocess.py` | create | PDF→images (pypdfium2), EXIF orientation, resize, HEIC support |
| `bill_reader/extract/base.py` | create | `Extractor` protocol, `ExtractionResult` |
| `bill_reader/extract/claude.py` | create | Claude tool-use extractor + prompt |
| `bill_reader/extract/prompts.py` | create | Extraction & categorisation prompts (LK/IN context, receipt pitfalls) |
| `bill_reader/extract/surya.py` | create | Optional Surya OCR extractor + box snapping |
| `bill_reader/extract/orchestrator.py` | create | Primary→fallback logic (FR-11), retry, records extractor used |
| `bill_reader/validate.py` | create | Arithmetic/date/VAT checks, confidence adjustment, warnings |
| `bill_reader/categorise.py` | create | Chart loading, supplier history, Claude classification, tax code rule |
| `bill_reader/worker.py` | create | Queue, thread pool, pipeline steps, status transitions, restart recovery |
| `bill_reader/export/base.py` | create | `VoucherSink` protocol |
| `bill_reader/export/myob_file.py` | create | Tab-delimited writer driven by YAML mapping; zip; batch marking |
| `bill_reader/app.py` | create | FastAPI app factory, startup (DB, worker, watcher) |
| `bill_reader/api.py` | create | JSON endpoints (see API Changes) |
| `bill_reader/web.py` | create | HTML routes |
| `bill_reader/templates/*.html` | create | `base`, `bills_list`, `bill_review`, `export`, `settings` |
| `bill_reader/static/review.js`, `static/app.css` | create | Image viewer, box overlay, confidence colours, account search |
| `bill_reader/cli.py` | create | `serve`, `eval`, `import-accounts` commands |
| `bill_reader/evaluate.py` | create | Eval runner + accuracy report vs ground truth |
| `config/chart_of_accounts.sample.csv` | create | Sample Sri Lankan SME chart (MYOB account-export columns) |
| `config/myob_import_formats.yaml` | create | Spend Money & Service Purchase column mappings |
| `config/tax_codes.yaml` | create | `VAT` 18%, `SSL` 2.5%, `N-T` |
| `samples/bills/*` | create (done) | Five sample bills supplied by the user |
| `samples/ground_truth/*.json` | create | Expected values per sample (incl. expected account code) |
| `tests/…` | create | Unit tests + recorded Claude fixtures in `tests/fixtures/` |

## Data Model Changes

New SQLite database `data/bill_reader.db`:

- **Bill**: `id`, `sha256` (unique), `original_filename`, `source` (`upload`/`inbox`), `stored_path`, `page_count`, `status` (`processing|needs_review|approved|exported|failed`), `error`, `extractor_used`, `overall_confidence`, `doc_type`, `languages`, `currency`, `exchange_rate` (Decimal, null), `voucher_type` (`spend_money` default / `purchase`), `paying_account`, `account_code`, `account_confidence`, `account_reason`, `tax_code`, `warnings` (JSON), `raw_extraction` (JSON), `export_batch_id`, `created_at`, `updated_at`.
- **BillField**: `bill_id`, `name` (supplier_name, supplier_tax_id, bill_number, bill_date, subtotal, discount, vat_amount, vat_rate, sscl_amount, total, …), `value` (str), `extracted_value`, `confidence`, `bbox` (JSON), `page`.
- **LineItem**: `bill_id`, `idx`, `description`, `description_original`, `qty`, `unit_price`, `amount`, `confidence`.
- **AuditEvent**: `bill_id`, `ts`, `action` (`extracted|corrected|approved|exported|reextracted`), `details` (JSON: field, old, new).
- **SupplierHistory**: `normalised_name` (PK), `display_name`, `last_account_code`, `last_tax_code`, `times_used`, `updated_at`.
- **Account**: `code`, `name`, `type`, `is_detail` (loaded from CSV; replaced on import).
- **ExportBatch**: `id`, `created_at`, `file_path`, `bill_count`.

Monetary columns use `Decimal` (stored as TEXT) per NFR-5.

## API Changes

New endpoints (JSON; HTML pages mirror them):

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/bills` | Multipart upload (1..n files) → created bill ids / duplicate info |
| GET | `/api/bills?status=` | List bills |
| GET | `/api/bills/{id}` | Bill with fields, line items, warnings, suggestion |
| GET | `/api/bills/{id}/pages/{n}` | Rendered page image |
| PATCH | `/api/bills/{id}` | Save corrections (fields, line items, account, tax code, voucher type, rate) |
| POST | `/api/bills/{id}/approve` | Validate required fields → `approved` |
| POST | `/api/bills/{id}/reextract` | Re-queue |
| DELETE | `/api/bills/{id}` | Delete |
| GET | `/api/accounts?q=` | Search chart of accounts |
| POST | `/api/accounts/import` | Upload MYOB accounts CSV |
| POST | `/api/exports` | Export approved bills → zip download |
| GET | `/api/exports` | List batches; `GET /api/exports/{id}` re-download |

## Key Decisions

1. **Frontier model first, Surya as fallback** (user decision). Classic OCR fails on handwritten Sinhala. Claude reads the whole document, understands layout (subtotal vs cash tendered) and returns structured output in one call.
2. **Forced tool use for structured output.** It guarantees schema-valid JSON and allows one retry with the validation error attached.
3. **Server-rendered UI, no SPA.** Fewer moving parts for a demo. Can be swapped later.
4. **SQLite + in-process worker.** Right-sized for ~50 bills/month and a single user.
5. **One account code per bill.** Line items are kept for display and as categorisation context only (A7).
6. **Config-driven MYOB import columns.** The exact AccountRight import layout depends on version (A1). A YAML mapping means AC-12 fixes are config-only.
7. **SSCL folded into the expense amount; only VAT is reported as tax** (A5).
8. **`VoucherSink` abstraction now.** Iteration 2's API posting plugs in without touching review or export flows.
9. **Recorded fixtures for tests.** CI and `pytest` never call the API (NFR-6). The live accuracy check is the explicit `bill-reader eval` command.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Handwritten Sinhala misread (sample 01) | Human review mandatory; confidence colouring; arithmetic checks flag inconsistent totals; report per-sample accuracy honestly in the eval |
| Model hallucinates plausible values | Validation checks; required fields need user confirmation when below 0.85 (amber/red block approval until touched) |
| Bounding boxes from the LLM are imprecise | Treated as best-effort hints; snapped to Surya boxes when available; never used for logic |
| MYOB import format mismatch | YAML mapping; AC-12 manual import test; sample output documented in README |
| Surya heavy (PyTorch) | Optional extra; lazy import; app degrades gracefully (NFR-2) |
| API outage or quota | Fallback path; bills stay `failed` with a retry button; never lose the original file |
| Sample set is tiny (5) | Eval harness makes adding bills trivial; Tamil-script sample still needed |
| Foreign-currency bills | Explicit exchange-rate entry; approval blocked until provided |
