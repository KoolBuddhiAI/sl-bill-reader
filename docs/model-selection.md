# Model selection: bill extraction

**Date:** 2026-10-19
**Decision:** read bills with **`gemini-3.8-flash`**. If it fails, fall back to **`deepseek-flash`**, then **`gpt-6-sol`**. Account codes come from `deepseek-flash` in text mode.
**Confidence:** moderate on the shortlist and low on the exact ranking. The comparison used 5 sample bills, with 1–3 runs per model.

## Results with cost (5 sample bills)

Full output: [eval-results.md](eval-results.md). Prices are from the providers' pricing pages on 2026-10-19.

| Model | Totals | Supplier | Bill no. | Per bill | Avg time | Status / notes |
|---|---|---|---|---|---|---|
| **gemini-3.8-flash** | **5/5** | **5/5** | **5/5** | **~$0.008** | 17 s | Current. Price doubles on 2027-01-01 (~$0.016/bill) |
| gemini-3.6-flash | 5/5 | 5/5 | 5/5 | ~$0.008 | 15 s | Previous generation Flash |
| gemini-3.5-flash-lite | 5/5 | 5/5 | 4/5 | ~$0.004 | **3 s** | Cheapest and fastest 5/5 on totals |
| deepseek-flash | 5/5 in all 3 runs | 3–5/5 | 5/5 | ~$0.008 | 15–22 s | Supplier spelling varies between runs; China-based provider |
| gpt-6-sol | 5/5 | 5/5 | 5/5 | ~$0.029 | 19 s | One earlier run read 7,220 instead of 7,226 |
| gpt-5.6-sol | 5/5 (2 runs) | 5/5 | 5/5 | ~$0.063 | 28 s | |
| gemini-4-argon | 5/5 | 5/5 | 5/5 | ~$0.022 | 37 s | Price doubles on 2026-12-01; no free tier |
| gpt-6-astra | 5/5 (2 runs) | 5/5 | 5/5 | ~$0.129 | 30 s | Most expensive |
| gpt-5.5 | 4–5/5 | 5/5 | 4–5/5 | ~$0.058 | 11–16 s | Read 7,126 instead of 7,226 on run 2. Was the default briefly; replaced |
| gpt-6-luna | 3–4/5 | 5/5 | 5/5 | ~$0.002 | 64 s | Cheapest, but misreads handwritten totals |
| gpt-5.4-mini | 4/5 | 4–5/5 | 3–4/5 | ~$0.006 | 4 s | Misreads handwritten totals |
| gemini-3.1-pro (preview) | — | — | — | — | >180 s | Timed out on 4 of 5 bills; excluded |

Every model scores about the same on dates (2–3/4) and account codes (3–4/5). The handwritten dates on samples 04 and 05 are genuinely ambiguous, and nearly every model reads sample 05 as 27/11/2016, so that ground-truth label may be wrong. On account codes, sample 02's items are "Sample Item 1–10", and sample 03 (groceries) can reasonably be either Purchases or Meals.

## Why gemini-3.8-flash

- It is one of only two models that got every money and identity field right in its run at the lowest cost tier (~$0.008/bill). The other is gemini-3.6-flash, the previous generation.
- It costs about 7× less than `gpt-5.5`, which also misread a handwritten total on its second run.
- Bigger was not better. `gpt-6-astra` costs 16× more for the same score, and the `gemini-3.1-pro` preview timed out.
- The fallbacks come from other vendors (DeepSeek, then OpenAI), so one provider's outage or rate limit doesn't stop processing.

At ~50 bills a month, the whole chain costs well under $1 a month. Cost becomes a deciding factor only at thousands of bills a month.

## Trade-offs and when to change

| If… | Then |
|---|---|
| Speed matters more, e.g. bulk back-loading | Use `gemini-3.5-flash-lite` (3 s/bill, half the cost; one bill number missed) |
| A cheaper option is wanted after the January 2027 price rise | `gemini-3.5-flash-lite` or `deepseek-flash` |
| Bills must not go to a China-based provider | Remove `deepseek-vision` from the fallback chain and categorisation, and use a Gemini or OpenAI model there |
| Gemini sends data to the free tier | **Make sure billing is enabled on the Gemini key before processing real customer invoices.** As I understand Google's terms, free-tier API content may be used to improve their products and paid-tier content is not. I'm moderately confident; check the current Gemini API terms. |

## Data governance

- Bill images are sent to the extraction provider: Google by default, and DeepSeek or OpenAI on fallback. The extracted text is sent to DeepSeek for account coding.
- Retention and training policies differ by provider and tier. Confirm them against the client's data-handling requirements (assumption A9 in the spec) before go-live.

## Not tested

- **GLM:** the Z.ai account had no credit.
- **Claude:** no `ANTHROPIC_API_KEY` was set.
- **Document-specialised OCR services** (e.g. Azure Document Intelligence, Google Document AI): none is available on the current keys, and their support for handwritten Sinhala is unverified.
- **Tamil-script bills:** none in the sample set.

Re-run `bill-reader eval samples/ --models …` once there are 30 or more real bills. Five samples can't reliably separate the top tier.
