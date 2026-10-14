# Proposal: Multilingual Bill Reader → MYOB Vouchers

**Created:** 2026-10-14
**Status:** 🟡 Draft

## Problem

Supplier bills and invoices come in many forms: formally printed, digital PDFs, phone photos, and scans. Many are handwritten (common for small Sri Lankan suppliers), and they can be in **English, Sinhala or Tamil**, sometimes mixed on one page. Today someone has to read each document, decide which account code it belongs to, and key it into MYOB by hand. That is slow and error-prone. It also needs Sinhala/Tamil literacy, and it leaves no record linking each voucher to its source document.

Commodity OCR tools (Tesseract, most cloud OCR) handle printed English well. They do badly on Sinhala and Tamil, and worst on handwriting. Published benchmarks only cover **printed** Sinhala/Tamil. Surya-OCR leads zero-shot tests, and fine-tuned LightOnOCR-2-1B leads on printed Sinhala pages. There is **no public benchmark for Sinhala/Tamil handwritten invoices**, so model choice has to be validated on our own documents.

## Proposed Solution

A small web app plus background worker that turns a document into a reviewed MYOB voucher:

```
 Ingest ──► Pre-process ──► Extract ──► Categorise ──► Review UI ──► Push to MYOB
 (upload /    (PDF→image,     (VLM reads    (suggest       (preview +     (Spend Money or
  watched      deskew, split   fields +      account code   confidence,    Purchase Bill,
  folder)      pages)          line items)   + tax code)    user edits)    attach source)
```

1. **Ingest:** drag-and-drop upload in the UI, plus a **watched folder** (local or network share) for scanner output. Accepts PDF (text and scanned), JPG/PNG/HEIC/TIFF. Uses a file hash to skip duplicates.
2. **Pre-processing:** rasterises PDFs; reads the text layer directly when one exists; deskews, crops and enhances contrast on photos; splits multi-page and multi-invoice PDFs.
3. **Extraction (the model question):** a pluggable `Extractor` interface with a tiered strategy:
   - **Primary: a frontier multimodal LLM** (e.g. Claude, or Gemini as an alternative) prompted for **structured JSON output**: supplier, invoice no., date, currency, line items, subtotal, tax/VAT, total. Each field gets its own confidence and a bounding box. These models currently handle handwritten Sinhala/Tamil far better than classic OCR, and they understand invoice layout without templates.
   - **Secondary / cross-check: Surya-OCR** (best open-source zero-shot printed Sinhala/Tamil OCR). It runs locally to give a raw text layer and an independent reading of the numbers. Where the two readings disagree, confidence is lowered.
   - **Optional later: a fine-tuned open VLM** (e.g. LightOnOCR-2 or Qwen-VL class) trained on our corrected documents, for on-prem or cheaper processing once we have enough labelled data.
   - **Confidence score** = blend of model self-reported confidence, OCR agreement, and arithmetic checks (line items add up to the subtotal, subtotal plus tax equals the total, the date is valid, the supplier's tax number has the right format).
4. **Categorisation:** suggests an MYOB **account code** and **tax code** per line or per bill. Inputs are the chart of accounts synced from MYOB, the supplier's history (the last code used for that supplier wins), and LLM classification of the item descriptions as a fallback. Each suggestion shows a confidence score and a short reason.
5. **Review UI:** the original image sits side by side with an editable form. Fields are colour-coded by confidence (green/amber/red), and hovering a field highlights where it was read on the image. The user corrects values, picks the account code from a searchable list, and approves. Low-confidence bills must be reviewed; nothing posts automatically in v1. Corrections are stored as a feedback dataset for evaluation and future fine-tuning.
6. **Push to MYOB:** OAuth 2.0 to the MYOB Business / AccountRight API (`sme-purchase`, `sme-banking` scopes). Creates a **Purchase Bill** (`/Purchase/Bill/Service`) or a **Spend Money** transaction (`/Banking/SpendMoneyTxn`), depending on the voucher type the user chooses. Matches or creates the supplier card and attaches the source document. Records the MYOB UID for traceability, and blocks duplicates using supplier + invoice no. + amount.

**Suggested stack (to confirm in /plan):** Python (FastAPI) backend + job queue, React/Next.js review UI, PostgreSQL, object storage for documents, Docker deploy.

## Scope

### In Scope
- Upload via web UI and watched-folder ingestion
- PDF (text and scanned) and image inputs; multi-page handling
- Printed and handwritten English, Sinhala and Tamil (including mixed-language bills)
- Field and line-item extraction with per-field confidence and source bounding boxes
- Account code and tax code suggestions using the MYOB chart of accounts and supplier history
- Review/correct/approve UI with an image preview
- Posting to MYOB as a Purchase Bill or Spend Money, with the document attached
- Duplicate detection, audit log (who changed what, what was posted)
- A labelled evaluation set (~100–200 real bills across language and print/handwriting mix) and a repeatable accuracy benchmark to pick and track models

### Out of Scope
- Fine-tuning our own model (follow-up once the correction dataset exists)
- Fully automatic posting without review
- Payment processing, bank reconciliation, approval workflows beyond a single reviewer
- Accounting systems other than MYOB (keep the connector interface pluggable)
- Mobile app (mobile browser upload is enough for v1)
- Email-inbox ingestion (candidate for v2)

## Impact

- **Files affected:** ~40–60 (new greenfield repo: backend, worker, UI, MYOB connector, eval harness)
- **Complexity:** large
- **Risk:** medium–high
  - *Handwriting accuracy* on Sinhala/Tamil is unproven. Mitigation: build the eval set first, keep a human in the loop, use confidence gating.
  - *Data privacy:* sending bills to a cloud LLM API. Mitigation: confirm the data policy; keep a local-only Surya path as an option.
  - *MYOB API constraints:* only company-file admins can authorise OAuth; rate limits; supplier card matching.
  - *Cost per document* for LLM calls (expected to be low cents per page; to be measured).

## Open Questions

1. **MYOB product:** MYOB Business / AccountRight (cloud) or MYOB Advanced? One company file or several?
2. **Voucher type:** should bills post as Purchase Bills (creditor, paid later) or Spend Money (already paid), or should the user choose per bill?
3. **Data residency:** is it acceptable to send invoice images to a cloud AI API (Anthropic/Google), or must processing stay on-prem?
4. **Volume:** roughly how many bills per month? This drives cost and whether a fine-tuned local model is worth it.
5. **Tax:** which Sri Lankan taxes appear (VAT, SSCL), and how do they map to MYOB tax codes?
6. **Line-level vs bill-level coding:** split one bill across several account codes, or one code per bill?
7. **Sample documents:** can you share 50+ real (or anonymised) bills covering the language and handwriting mix? This is needed for the model bake-off.
8. **Deployment:** where should it run (cloud VM, office server, Azure)? How many users, and is single sign-on needed?

### References
- [Benchmarking OCR Models for Sinhala and Tamil Document Digitization](https://www.researchgate.net/publication/391058761_Benchmarking_OCR_Models_for_Sinhala_and_Tamil_Document_Digitization)
- [Zero-shot OCR Accuracy of Low-Resourced Languages: Sinhala and Tamil](https://arxiv.org/pdf/2507.18264)
- [Cross-Temporal Sinhala OCR: Page-Level Adaptation (LightOnOCR-2 fine-tune)](https://arxiv.org/html/2606.29378)
- [uTHCD: Tamil Handwritten OCR benchmark](https://arxiv.org/pdf/2103.07676)
- [MYOB API: Spend Money](https://developer.myob.com/api/accountright/v2/banking/spend_money/) · [Purchase Bill](https://developer.myob.com/api/accountright/v2/purchase/bill/bill_item/)

---

**To proceed:** Review this proposal and approve to begin planning.
