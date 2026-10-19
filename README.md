# Bill Reader → MYOB vouchers

Reads supplier bills, invoices and receipts and turns them into MYOB AccountRight vouchers. Bills can be printed, thermal-printed or handwritten; PDF or image; in English, Sinhala or Tamil.

1. **Ingest:** upload in the browser, or drop files into the `inbox/` folder (PDF, JPG, PNG, TIFF, HEIC, WEBP). Duplicate files are detected and skipped.
2. **Read:** an AI model chosen in config reads the bill (GLM, DeepSeek, OpenAI or Claude). Each field gets a confidence score, and arithmetic/date/VAT checks lower the score when something doesn't add up.
3. **Categorise:** suggests one MYOB account and tax code per bill. A supplier's previous choice is reused; otherwise the model picks from your chart of accounts.
4. **Review:** the original image sits next to an editable form. Fields are coloured green/amber/red by confidence, and hovering a field highlights where it was read on the image.
5. **Export:** approved bills become AccountRight **import files** (Spend Money by default, Purchases for bills marked as purchase bills). Iteration 2 will post them through the MYOB API instead.

## Quick start

```bash
cp .env.example .env            # add at least one API key (see "Models")
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
bill-reader models check        # probes each model that has a key
bill-reader serve               # http://127.0.0.1:8000
```

With Docker: `docker compose up --build`. This mounts `data/`, `inbox/` and `config/`.

All data stays local:
- SQLite database: `data/bill_reader.db`
- Original files and rendered pages: `data/documents/`
- Export batches: `data/exports/`

## Models

Models are named **profiles** in [`config/models.yaml`](config/models.yaml). Each profile sets the provider, base URL, model id, the environment variable that holds its key, and what it can do. Changing models needs no code changes.

| Profile | Model | Key | Reads images |
|---|---|---|---|
| `glm-vision` | Z.ai `glm-4.6v` | `ZAI_API_KEY` | yes |
| `glm-vision-flash` | Z.ai `glm-4.6v-flash` | `ZAI_API_KEY` | yes |
| `deepseek-vision` (default) | `deepseek-flash` | `DEEPSEEK_API_KEY` | yes |
| `deepseek-text` (categorisation) | `deepseek-flash` (text mode) | `DEEPSEEK_API_KEY` | no: OCR + text mode, needs Surya |
| `openai-vision` | set your model | `OPENAI_API_KEY` | yes |
| `claude-vision` | `claude-opus-5-5` | `ANTHROPIC_API_KEY` | yes |

The active profile is chosen in this order:
1. The **Settings page**, saved in `data/active_models.json`.
2. `BILL_READER_EXTRACTION_PROFILE` / `BILL_READER_CATEGORISATION_PROFILE`.
3. `extraction:` / `categorisation:` in `models.yaml`.

If the active profile errors or its confidence is too low, `fallback_chain` lists the profiles to try next. On the review page, **Re-extract with…** re-runs a single bill with another model.

To add a model, add a profile. Any OpenAI-compatible endpoint works with `provider: openai_compatible`. Structured output uses tool calling, JSON mode or prompt-only JSON, depending on the `supports_*` flags. Model ids and endpoints change often, so run `bill-reader models check` after editing.

### Comparing accuracy

```bash
bill-reader eval samples/ --models glm-vision,glm-vision-flash,deepseek-vision
```

This runs every sample bill through each profile and scores supplier, bill number, date, total, VAT, currency and account code against `samples/ground_truth/`. It also reports latency, tokens and estimated cost. Results go to `docs/eval-results.md` and `data/eval/*.json`; the JSON includes the raw model output. Profiles without a key are listed as skipped.

### Surya OCR (optional)

`pip install -e '.[surya]'` enables:
- the fallback for when no vision model is reachable;
- **OCR + text** mode, which lets text-only models such as `deepseek-chat` extract bills.

The adapter targets `surya-ocr` 0.22. That version is a vision-language model that runs on an inference backend: vLLM on an NVIDIA GPU, llama.cpp otherwise. It also pins `pillow<11`, so install it in its own environment if you hit dependency conflicts.

The Surya adapter has only been tested with mocked predictors. Verify it on a machine where Surya is installed.

## Importing into MYOB AccountRight

1. In the app, approve bills, then **Export → Export approved bills**. You get `myob-export-batch-<n>.zip` containing `SpendMoney.txt` and/or `Purchases.txt`.
2. In AccountRight: **File → Import Data → Spend Money** (or **Purchases → Service Purchases**).
3. Choose *Tab-delimited* with a header record, then match the fields. The column headers come from [`config/myob_import_formats.yaml`](config/myob_import_formats.yaml).
4. Try it on a **test company file** first. If AccountRight rejects a column, fix the mapping in the YAML; no code change is needed. Columns marked `# verify against AccountRight version` are the uncertain ones.

Format details:
- Amounts are tax-inclusive in home currency (LKR).
- VAT goes in the tax amount column. SSCL stays inside the expense amount.
- Foreign-currency bills are converted at the rate you enter, and the memo records the original amount (`| Orig INR 7,226.00 @ 3.45`).

To use your own chart of accounts, export it from MYOB and upload it on the **Settings** page, or run `bill-reader import-accounts accounts.csv`. Until then, the sample Sri Lankan SME chart in `config/chart_of_accounts.sample.csv` is used.

## Assumptions to confirm with the client

| # | Assumption |
|---|---|
| A1 | MYOB AccountRight desktop (on-prem, 2019+), import via *File → Import Data* |
| A2 | The sample chart of accounts is used until the client's MYOB export is imported |
| A3 | Spend Money is paid from `1-1110 Cash at Bank` (`BILL_READER_DEFAULT_PAYING_ACCOUNT`) |
| A4 | Tax codes `VAT` (18%), `SSL` (SSCL 2.5%), `N-T` (no tax), see `config/tax_codes.yaml` |
| A5 | SSCL is a non-recoverable cost included in the expense; only VAT is claimed |
| A6 | Home currency is LKR; other currencies need an exchange rate before approval |
| A7 | One account code per bill (no line splitting) |
| A8 | Single user, local, no login |
| A9 | Invoice images may be sent to the cloud model provider |

## Development

```bash
python -m pytest -q             # offline: model calls use fakes and recorded fixtures
```

The code is laid out as follows:
- `bill_reader/llm/`: model profiles and provider adapters
- `bill_reader/extract/`: vision and OCR+text extractors, plus the fallback chain
- `bill_reader/validate.py`: confidence checks
- `bill_reader/categorise.py`: account and tax code suggestions
- `bill_reader/export/`: MYOB import file writer (`VoucherSink`)
- `bill_reader/worker.py`: background pipeline
- `bill_reader/api.py`: JSON API
- `bill_reader/web.py` + `templates/`: user interface

## Roadmap (iteration 2)

- Post vouchers directly through the AccountRight API with a `MyobApiSink`, alongside the file export.
- Live sync of the chart of accounts and supplier cards; store MYOB UIDs.
- Split one bill across several account codes.
- Add Tamil-script sample bills to the evaluation set.
