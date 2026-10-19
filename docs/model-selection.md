# Model selection: bill extraction

**Date:** 2026-10-19
**Decision:** read bills with **`gpt-5.5`**. If it fails, fall back to **`deepseek-flash`**, then **`gpt-5.6-sol`**. Account codes come from `deepseek-chat`.
**Confidence:** low to moderate. The comparison used 5 sample bills and one run per model (see below).

## Results (5 sample bills, one run each)

Full output: [eval-results.md](eval-results.md)

| Model | Totals | Supplier | Bill no. | Dates* | Account* | Avg time / bill | Notes |
|---|---|---|---|---|---|---|---|
| **gpt-5.5** | **5/5** | **5/5** | **5/5** | 2/4 | 4/5 | 11 s | Best overall; tool calling works |
| deepseek-flash | 5/5 | 3/5 † | 5/5 | 2/4 | 4/5 | 15 s | Cheapest (~$0.03 for 5 bills); supplier spelling varies between runs |
| gpt-5.6-sol | 5/5 | 5/5 | 5/5 | 2/4 | 4/5 | 26 s | Same accuracy as gpt-5.5, but over twice as slow |
| gpt-6-astra | 5/5 | 5/5 | 5/5 | 2/4 | 4/5 | 31 s | Same accuracy, slowest of the 5/5 group |
| gpt-6-sol | 4/5 | 5/5 | 5/5 | 2/4 | 4/5 | 16 s | Sample 04: 7,220 instead of 7,226 |
| gpt-6.1-sol | 4/5 | 5/5 | 5/5 | 2/4 | 3/5 | 36 s | Newest model, but slowest and missed sample 04 |
| gpt-4.1 | 4/5 | 5/5 | 4/5 | 2/4 | 4/5 | 4 s | Older baseline |
| gpt-5.6-terra | 4/5 | 5/5 | 4/5 | 2/4 | 4/5 | 12 s | |
| gpt-5.6-luna | 4/5 | 5/5 | 3/5 | 2/4 | 4/5 | 17 s | |
| gpt-5.4-mini | 4/5 | 4/5 | 4/5 | 2/4 | 3/5 | 4 s | Fast, but misses handwriting |
| gpt-6-luna | 3/5 | 5/5 | 5/5 | 2/4 | 4/5 | 25 s | Read 44,800 as 144,800 |

\* Two caveats on these columns:
- **Dates:** the handwritten dates on samples 04 and 05 are genuinely ambiguous. On sample 05, 9 of 11 models read "27/11/2016", while the ground truth says "27/1/2016". The label may be wrong, so the date column is not a useful way to tell models apart.
- **Account:** sample 02's line items are literally "Sample Item 1–10", so Suspense (`6-9999`) is a reasonable answer. That miss affects every model equally.

† DeepSeek got 5/5 suppliers in an earlier run the same day.

## Why gpt-5.5

- It is the only model that got every money and identity field right (totals, supplier, bill number) while staying fast (~11 s).
- Newer or larger models were **not** more accurate here. `gpt-6.1-sol` and `gpt-6-luna` both misread the handwritten total on sample 04, and they are 2–3× slower.
- The fallback uses a different vendor (DeepSeek), so an OpenAI outage or rate limit doesn't stop processing.

## Trade-offs and when to change

| Factor | gpt-5.5 | deepseek-flash |
|---|---|---|
| Accuracy on samples | 5/5 totals, most stable | 5/5 totals; supplier name varies |
| Latency | ~11 s | ~15 s |
| Cost | Not measured (prices aren't set in `config/models.yaml`). At ~50 bills/month the token use (~3.7k in / 1.1k out per bill) should cost cents to low dollars per month. | ~$0.006 per bill |
| Data handling | Bill images go to OpenAI | Bill images go to DeepSeek (China-based provider) |

- **Switch the default to DeepSeek** if OpenAI cost or data-residency terms become a concern. Its totals were just as accurate.
- **Re-run the comparison** (`bill-reader eval samples/ --models …`) once there are 30 or more real bills, especially Tamil-script and more handwritten Sinhala ones. Five samples are too few to separate the top four models with confidence.

## Not tested

- **GLM** (`glm-4.6v`): the Z.ai account had no credit, and the free `glm-4.6v-flash` tier was overloaded.
- **Claude**: no `ANTHROPIC_API_KEY` was set.
- **Tamil-script bills**: none in the sample set.
