# Spec: Multilingual Bill Reader → MYOB Vouchers (Iteration 1)

**Change:** bill-reader-myob-vouchers
**Created:** 2026-10-14
**Status:** 🟡 Draft

## Overview

A local, single-user web app that ingests bills/invoices (printed, thermal, handwritten; PDF or image; English, Sinhala, Tamil), extracts the voucher fields with a frontier multimodal model (Surya-OCR as fallback), proposes **one MYOB account code + tax code per bill**, lets the user review and correct the values against the original image with per-field confidence, and exports approved bills as **MYOB AccountRight import files** (Spend Money by default, Purchase Bill optional). Direct MYOB API posting is iteration 2 and is **not** part of this spec.

The goal of iteration 1 is a **capability demo** on the five sample bills supplied (see *Sample Set*).

### Assumptions (user said "assume these" — each is configurable)

| # | Topic | Assumption |
|---|-------|------------|
| A1 | MYOB version | AccountRight desktop (on-prem, 2019+). Import via *File → Import Data* using MYOB's tab-delimited text import format. Column layout kept in a config file so it can be adjusted without code changes. |
| A2 | Chart of accounts | No MYOB export available yet → ship a **sample Sri Lankan SME chart of accounts** (CSV in MYOB account-export shape). User can replace it by importing their own MYOB accounts export. |
| A3 | Spend Money bank account | Default paying account `1-1110 Cash at Bank` (configurable). |
| A4 | Tax codes | `VAT` = VAT 18%; `SSL` = SSCL 2.5%; `N-T` = not reportable / no tax. Names configurable. |
| A5 | SSCL treatment | SSCL is a non-recoverable cost → included in the expense allocation amount. VAT is the only separately claimable tax amount on the voucher. |
| A6 | Currency | Home currency LKR. Bills in another currency (e.g. INR samples 04, 05) are detected and flagged; the user enters an exchange rate and the exported amount is LKR, with the original currency/amount written into the memo. |
| A7 | Coding granularity | One account code per bill (no line splitting). Line items are extracted for display and categorisation only. |
| A8 | Users / deployment | One user on one machine; no login. Started with `docker compose up` or `uvicorn`. |
| A9 | AI provider | Anthropic API (Claude) via API key in `.env`; model name configurable. Images may be sent to the cloud (approved). |

## Sample Set

Stored in `samples/bills/` with ground truth in `samples/ground_truth/*.json`.

| File | Kind | Language | Key expected values |
|------|------|----------|---------------------|
| `01-saman-motors-si-handwritten.jpg` | Handwritten on printed form, watermarked photo | Sinhala | Supplier *Saman Motors* (Monaragala, Hero dealer), bill no. `8502`, total **44,800.00 LKR** (list 46,530 less discounts); category → Motor Vehicle Repairs |
| `02-vat-company-en-printed-tax-invoice.png` | Printed tax invoice | English | Supplier *Vat Company (Pvt) Ltd*, TIN `11C011096`, invoice `T-10001`, date `2026-01-04`, subtotal **2,305,000.00**, VAT 18% **414,900.00**, total **2,719,900.00** (note malformed "2,30,5000.00" and lakh-style grouping) |
| `03-malindu-spice-hut-si-thermal.png` | Thermal POS receipt | Sinhala | Supplier *Malindu Spice Hut*, bill `1000013`, date `2026-08-13`, total **510.00 LKR** — must **not** pick cash tendered (1,000.00), change (490.00) or "you saved" (210.00); category → Meals & Entertainment |
| `04-samsuddin-siddiqui-en-handwritten-inr.png` | Handwritten on printed form | English | Supplier *Samsuddin Siddiqui* (Mumbai), bill `287`, date `2024-10-28`, 9 lines, total **7,226 INR**; category → Repairs & Maintenance |
| `05-sea-rock-restaurant-en-handwritten-inr.png` | Handwritten cash bill | English (Tamil Nadu) | Supplier *Sea Rock Restaurant*, no. `4931`, total **340 INR**, 5 lines; category → Meals & Entertainment |

> No Tamil-script sample exists yet; Tamil support is a prompt/model capability, verified when a sample is provided (see Notes).

## Requirements

### Functional Requirements

**Ingestion**
- **FR-1** Upload one or more files via the web UI (drag-and-drop + file picker).
- **FR-2** Watch a configurable inbox folder; new files are ingested automatically and moved to `inbox/processed/` (or `inbox/failed/`).
- **FR-3** Accept PDF (text and scanned), JPG, PNG, TIFF, HEIC/HEIF, WEBP. Reject other types with a clear message.
- **FR-4** Detect duplicate files by SHA-256 and do not re-process them (show link to existing bill).

**Pre-processing**
- **FR-5** Convert each PDF page to an image (≥200 DPI); multi-page PDFs are treated as one bill with all pages sent to the extractor.
- **FR-6** Normalise images: apply EXIF orientation, downscale to a max long edge (default 2000 px), convert to JPEG/PNG for the model.

**Extraction**
- **FR-7** Extract a structured `BillExtraction`: supplier name, supplier address, supplier tax ID (TIN/VAT no.), bill/invoice number, bill date (ISO), currency (ISO 4217), detected language(s), document type (tax invoice / invoice / receipt / cash bill), line items (description, original-script description, qty, unit price, amount), subtotal, discount, VAT amount + rate, SSCL amount, total, payment method if shown.
- **FR-8** Each top-level field carries a confidence (0–1) and an optional normalised bounding box (`[x0,y0,x1,y1]`, 0–1, page index).
- **FR-9** Descriptions in Sinhala/Tamil are returned both as read (original script) and translated to English.
- **FR-10** Primary extractor is a frontier multimodal model (Claude) using a strict JSON schema / tool-call output.
- **FR-11** Fallback: if the primary extractor errors, times out, returns invalid JSON after one retry, or overall confidence < configurable threshold (default 0.5), run **Surya-OCR** locally and re-run extraction with the OCR text supplied as additional context (or, if the primary model is unavailable, produce a best-effort text-only extraction). The extractor used is recorded on the bill.
- **FR-12** Validation checks adjust confidence and raise warnings: Σ line amounts ≈ subtotal; subtotal − discount + VAT + SSCL ≈ total (tolerance 1.00); date parseable and not in the future; VAT amount ≈ rate × taxable amount; total > 0.

**Categorisation**
- **FR-13** Load chart of accounts from a CSV (sample SL SME chart shipped; user can upload their MYOB accounts export). Only expense/cost-of-sales/asset accounts that are "detail" accounts are selectable.
- **FR-14** Propose one account code per bill with confidence and a one-line reason, using in order: (a) supplier history — last approved code for the same normalised supplier name (confidence 0.95); (b) LLM classification of supplier + line items against the chart of accounts.
- **FR-15** Propose tax code: `VAT` when a VAT amount > 0 is present, else `N-T` (A4/A5).

**Review**
- **FR-16** Bill list page: thumbnail, supplier, date, total, currency, overall confidence, status (`processing`, `needs_review`, `approved`, `exported`, `failed`), filter by status.
- **FR-17** Review page: original image (zoom/pan, page switch) beside an editable form of all FR-7 fields and line items; each field coloured green (≥0.85), amber (0.6–0.85), red (<0.6); hovering/focusing a field draws its bounding box on the image when available.
- **FR-18** Validation warnings (FR-12) shown at the top of the review page.
- **FR-19** Searchable account-code picker; tax-code picker; voucher type toggle **Spend Money (default) / Purchase Bill**; paying account (Spend Money) defaulting to A3; exchange-rate input shown when currency ≠ LKR.
- **FR-20** "Approve" saves corrections, stores original vs corrected values per field, updates supplier history, sets status `approved`. "Re-extract" re-runs extraction. "Delete" removes the bill.

**Export**
- **FR-21** Export all `approved` bills to MYOB AccountRight import files: one tab-delimited `.txt` for Spend Money and one for Purchases (Service), downloaded as a single `.zip` when both exist. Column mapping is defined in `config/myob_import_formats.yaml`.
- **FR-22** Each exported voucher: date, supplier (Co./Last Name), reference (bill no.), memo (`<supplier> <bill no.>` + original currency note if converted), allocation account, amount (tax-inclusive LKR), tax code, VAT amount; Spend Money also paying account; Purchase also supplier invoice no.
- **FR-23** Exported bills are marked `exported` with export batch id/time and are excluded from subsequent exports unless the user explicitly re-exports a batch.

**Evaluation**
- **FR-24** A CLI `bill-reader eval samples/` runs the pipeline on the sample set and reports per-field accuracy against ground truth (supplier, bill no., date, total, currency, account code) and extractor used.

### Non-Functional Requirements

- **NFR-1** Processing time per single-page bill ≤ 30 s with the primary extractor (excluding Surya cold start).
- **NFR-2** Runs on a laptop (8 GB RAM) without GPU; Surya fallback is an optional install (`pip install .[surya]`) and the app runs without it (fallback reported as unavailable).
- **NFR-3** Secrets only from environment/`.env`; `.env` gitignored; no API key in logs.
- **NFR-4** All original files retained unmodified under `data/documents/` for audit; every field correction and export is logged with timestamp.
- **NFR-5** Amounts stored as `Decimal` (never float); export uses 2 decimal places and `.` decimal separator, no thousands separators.
- **NFR-6** Unit tests run offline (LLM responses mocked from recorded fixtures); `pytest` passes with no network.
- **NFR-7** UI usable in a current Chrome/Edge at ≥1280 px wide; Sinhala/Tamil text renders (Noto Sans Sinhala / Noto Sans Tamil).

## Acceptance Criteria

- [ ] **AC-1** Uploading all five sample files via the UI produces five bills that reach `needs_review` (or `failed` with a visible reason); re-uploading any of them is rejected as duplicate.
- [ ] **AC-2** Dropping a sample file into the watched inbox folder creates a bill within 10 s of the file being written, and the file is moved to `processed/`.
- [ ] **AC-3** A single-page PDF made from sample 02 is processed identically to the PNG (same total/VAT).
- [ ] **AC-4** On the live eval (`bill-reader eval samples/`), **total** is correct on ≥4/5 samples and **supplier name** recognisably correct on ≥4/5; sample 03 total is 510.00 (not 1,000.00 / 490.00 / 210.00).
- [ ] **AC-5** Sample 02 extraction: subtotal 2,305,000.00, VAT 414,900.00 @ 18%, total 2,719,900.00, tax code `VAT`, no arithmetic warning.
- [ ] **AC-6** Samples 04 and 05 are detected as `INR`; the review page requires an exchange rate before approval; the export amount equals total × rate rounded to 2 dp and the memo contains the original INR amount.
- [ ] **AC-7** Every extracted field shows a confidence colour; at least the total field on sample 02 highlights a box on the image when hovered.
- [ ] **AC-8** Proposed account codes on the live eval match the expected category for ≥4/5 samples (01 vehicle repairs, 02 purchases/cost of sales, 03 & 05 meals, 04 repairs & maintenance).
- [ ] **AC-9** After approving a bill from supplier X with code C, a new bill from supplier X is proposed code C with reason "previously used for this supplier".
- [ ] **AC-10** With the primary extractor forced to fail (invalid API key / test flag) and Surya installed, a sample is still extracted via `surya` and the bill shows "Extracted with: Surya fallback". Without Surya installed, the bill goes to `failed` with a clear message.
- [ ] **AC-11** Export of approved samples produces Spend Money and Purchase files whose columns match `config/myob_import_formats.yaml`, tab-delimited, one voucher per record, amounts with 2 dp; a second export without new approvals produces nothing; exported bills show `exported`.
- [ ] **AC-12** The generated Spend Money file imports into an AccountRight sample company file without errors *(manual check — requires MYOB; recorded in verify-report)*.
- [ ] **AC-13** `pytest` passes offline; corrections are persisted (original vs corrected visible in the bill's audit log).

## Edge Cases

- Thermal receipts showing cash tendered / change / savings larger than the total (sample 03).
- Lakh/Indian digit grouping (`2,30,5000.00`, `27,19,900.00`) and malformed separators (sample 02).
- Two amount columns (list price vs. discounted) on handwritten forms — the payable total is the discounted one (sample 01).
- Ambiguous / partially written dates (`26/9/6`, `27/1/2016`) → low confidence, user confirms; dd/mm assumed for LK/IN.
- Watermarked or skewed photos, fingers in frame, background clutter (samples 01, 03, 05).
- Handwritten totals scribbled across the page (e.g. circled "44,800") vs. the printed total box.
- Bills with no supplier tax ID, no bill number, or no date → field empty with confidence 0, approval still allowed except for total and date (required).
- Multiple bills in one image/PDF → out of scope; user warned if the model reports >1 document.
- Non-bill images → document type `not_a_bill`, bill marked `failed`.
- Model returns a currency symbol only (`Rs`) → resolved by supplier country context (LK → LKR, IN → INR), flagged amber.
- File written slowly into inbox → wait until size is stable before ingesting.
- Supplier name in Sinhala vs English across bills → history lookup uses normalised English name.

## Dependencies

- Anthropic API key (Claude) — primary extractor and categoriser.
- Python 3.11+, FastAPI, Uvicorn, SQLModel/SQLite, Pydantic v2, Jinja2, `pypdfium2`, Pillow + `pillow-heif`, `watchdog`, `anthropic` SDK.
- Optional: `surya-ocr` (+ PyTorch CPU) for fallback.
- MYOB AccountRight desktop with a test company file for AC-12 (manual).

## Notes

- **Out of scope (iteration 2):** MYOB AccountRight API posting, live chart-of-accounts/supplier sync, supplier card creation, MYOB UIDs.
- **Tamil script:** collect at least one Tamil-script bill before verifying iteration 1; add it to the eval set.
- **Assumptions A1–A6** must be confirmed with the client before production use; the import column mapping (A1) is the most likely to need adjustment after AC-12.
