# Proposal: Multilingual Bill Reader → MYOB Vouchers

**Created:** 2026-10-14
**Status:** 🟡 Draft (revised after review)

## Problem

Supplier bills and invoices come in many forms: formally printed, digital PDFs, phone photos, and scans. Many are handwritten (common for small Sri Lankan suppliers), and they can be in **English, Sinhala or Tamil**, sometimes mixed on one page. Today someone has to read each document, decide which account code it belongs to, and key it into MYOB by hand. That is slow and error-prone. It also needs Sinhala/Tamil literacy, and it leaves no record linking each voucher to its source document.

Commodity OCR tools (Tesseract, most cloud OCR) handle printed English well. They do badly on Sinhala and Tamil, and worst on handwriting. Published benchmarks only cover **printed** Sinhala/Tamil. Surya-OCR leads zero-shot tests, and fine-tuned LightOnOCR-2-1B leads on printed Sinhala pages. There is **no public benchmark for Sinhala/Tamil handwritten invoices**, so model choice has to be validated on our own documents.

## Decisions (review 2026-10-14)

| # | Question | Decision |
|---|----------|----------|
| 1 | MYOB product | **MYOB AccountRight on-premise** (desktop company file) |
| 2 | Voucher type | User chooses per bill; **default = Spend Money** (Purchase Bill as option) |
| 3 | Cloud AI | Acceptable — invoice images may be sent to a cloud AI API |
| 4 | Volume | ~50 bills / month (cost is not a concern; no fine-tuning needed) |
| 5 | Taxes | VAT and SSCL appear on bills and map to MYOB tax codes |
| 6 | Coding | **One account code per bill** (line-splitting deferred) |
| 7 | Sample docs | None yet — start with a synthetic/sample set we create |
| 8 | SSO / deployment | Not in the initial version — runs locally (single user) |

**Iteration 1 goal:** *demonstrate capability* — read the invoice, propose an account code, let the user review/correct, and **export a file that MYOB AccountRight can import**. Direct API posting is **iteration 2**.

## Proposed Solution

```
 Ingest ──► Pre-process ──► Extract ──► Categorise ──► Review UI ──► Export MYOB import file  (iter 1)
 (upload /    (PDF→image,     (frontier     (one account    (preview +                          └─► MYOB API  (iter 2)
  folder)      deskew)         VLM; Surya    code + tax      confidence,
                               fallback)     code / bill)    edit, approve)
```

1. **Ingest** — drag-and-drop upload in a local web UI, plus a watched folder for scanner output. PDF (text + scanned) and JPG/PNG/HEIC/TIFF. Duplicate detection by file hash.
2. **Pre-processing** — rasterise PDFs, use embedded text layer when present, deskew/contrast-enhance photos, handle multi-page bills.
3. **Extraction** — pluggable `Extractor` interface:
   - **Primary: frontier multimodal LLM** (Claude; Gemini as swappable alternative) returning **structured JSON**: supplier, invoice no., date, currency, line items, subtotal, **VAT**, **SSCL**, total — each with a per-field confidence and bounding box. Handles printed and handwritten English/Sinhala/Tamil without templates.
   - **Fallback: Surya-OCR** (local, best open-source printed Sinhala/Tamil OCR) — used when the frontier model fails, errors, or returns low confidence; its text layer is fed back for a second extraction pass.
   - **Confidence** = model self-confidence + arithmetic checks (lines → subtotal, subtotal + VAT + SSCL → total), date validity, VAT-number format.
4. **Categorisation** — propose **one account code + tax code per bill**, using: the chart of accounts **imported from an MYOB export file** (no API in iter 1), supplier history (last code used for that supplier), and LLM classification of the item descriptions as fallback. Shows confidence + a one-line reason.
5. **Review UI** — original image beside an editable form; fields colour-coded by confidence (green/amber/red), hover highlights the source region; searchable account-code picker; voucher-type toggle (**Spend Money** default / Purchase Bill); approve. Corrections are saved (future accuracy tracking).
6. **Export (iteration 1)** — generate MYOB AccountRight **import files** (tab-delimited text in MYOB's import format, via *File → Import Data*):
   - Spend Money import (default), and Purchases (Service bill) import for bills flagged as Purchase Bill.
   - Approved bills batched into one file per voucher type; bills marked as exported to prevent double-import.
   - Exact field layout / required columns to be confirmed against the MYOB AccountRight import/export guide during `/specclaw:plan`.
7. **MYOB API (iteration 2, planned not built)** — AccountRight on-prem exposes the API via the local AccountRight API service; post Spend Money (`/Banking/SpendMoneyTxn`) or Purchase Bill (`/Purchase/Bill/Service`) directly, sync chart of accounts and supplier cards live, store MYOB UIDs. The export step sits behind a `VoucherSink` interface so the API sink drops in alongside the file sink.

**Suggested stack (confirm in /plan):** Python (FastAPI) backend with a background worker, lightweight React review UI, SQLite (single user, local), local file storage, Docker Compose for one-command start.

## Scope

### In Scope (iteration 1)
- Upload via UI and watched-folder ingestion; PDF + image inputs
- Printed and handwritten English, Sinhala, Tamil (including mixed)
- Frontier-VLM extraction with per-field confidence; Surya-OCR fallback
- VAT and SSCL extraction and tax-code mapping
- One account code per bill, proposed from imported chart of accounts + supplier history + LLM
- Review/correct/approve UI with image preview and confidence colouring
- Voucher type per bill (Spend Money default / Purchase Bill)
- Export of MYOB AccountRight import files; exported-status tracking
- A small **sample document set** (synthetic + any anonymised real bills later) and a simple accuracy script

### Out of Scope (iteration 1)
- **Direct MYOB API posting** → iteration 2
- Splitting one bill across multiple account codes
- SSO, multi-user, cloud deployment
- Fine-tuning models
- Automatic posting without review
- Payments, reconciliation, approval workflows; non-MYOB systems; email ingestion

## Impact

- **Files affected:** ~30–40 (greenfield: backend, worker, UI, extractor, categoriser, MYOB export, samples)
- **Complexity:** medium (iteration 1); large overall with iteration 2
- **Risk:** medium
  - *Handwritten Sinhala/Tamil accuracy* unproven — mitigated by human review, confidence gating, Surya fallback, and testing on a sample set.
  - *No real samples yet* — synthetic samples may overstate accuracy; ask for real bills before go-live.
  - *MYOB import format strictness* — import files fail on wrong column order/date format/account numbers; validate against a test company file.
  - *Iteration 2:* on-prem API requires the AccountRight API service running and reachable from the app host.

## Open Questions

1. **MYOB version** — which AccountRight version is installed (e.g. AccountRight 20xx desktop / "AccountRight Live" with local file)? Affects import format and iteration-2 API access.
2. **Chart of accounts** — can you export the chart of accounts (and supplier card list) from MYOB so we can seed the categoriser? Otherwise we'll ship a sample Sri Lankan SME chart.
3. **Spend Money bank account** — which MYOB bank/cash account should Spend Money vouchers be paid from by default?
4. **Tax codes** — the exact MYOB tax code names used for VAT and SSCL (e.g. `VAT`, `SSL`), and how bills with no VAT should be coded.
5. **Currency** — LKR only, or foreign-currency bills too?
6. **Sample bills** — when available, even 10–20 real bills (photo/scan) would significantly improve the demo's credibility.

### References
- [Benchmarking OCR Models for Sinhala and Tamil Document Digitization](https://www.researchgate.net/publication/391058761_Benchmarking_OCR_Models_for_Sinhala_and_Tamil_Document_Digitization)
- [Zero-shot OCR Accuracy of Low-Resourced Languages: Sinhala and Tamil](https://arxiv.org/pdf/2507.18264)
- [Cross-Temporal Sinhala OCR: Page-Level Adaptation (LightOnOCR-2 fine-tune)](https://arxiv.org/html/2606.29378)
- [uTHCD: Tamil Handwritten OCR benchmark](https://arxiv.org/pdf/2103.07676)
- [MYOB API: Spend Money](https://developer.myob.com/api/accountright/v2/banking/spend_money/) · [Purchase Bill](https://developer.myob.com/api/accountright/v2/purchase/bill/bill_item/)

---

**To proceed:** Review this proposal and approve to begin planning.
