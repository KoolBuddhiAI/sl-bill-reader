# Model comparison on the sample bills

Generated 2026-10-19 02:34 UTC by `bill-reader eval`. Account codes suggested by the `deepseek-text` profile in every run.

## Accuracy per field

| Profile | Model | Mode | supplier_name | bill_number | bill_date | total | vat_amount | currency | account_code | Mean latency | Tokens in/out | Est. cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-vision | deepseek-flash | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 12172 ms | 26676/14519 | $0.0232 |
| openai-vision | gpt-4.1 | vision | 5/5 | 4/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 4432 ms | 18620/3582 | – |

## Total read per sample

| Sample | Expected | deepseek-vision | openai-vision |
|---|---|---|---|
| 01-saman-motors-si-handwritten.jpg | 44800.00 LKR | ✅ 44800.00 | ✅ 44800.00 |
| 02-vat-company-en-printed-tax-invoice.png | 2719900.00 LKR | ✅ 2719900.00 | ✅ 2719900.00 |
| 03-malindu-spice-hut-si-thermal.png | 510.00 LKR | ✅ 510.00 | ✅ 510.00 |
| 04-samsuddin-siddiqui-en-handwritten-inr.png | 7226.00 INR | ✅ 7226.00 | ❌ 7926.00 |
| 05-sea-rock-restaurant-en-handwritten-inr.png | 340.00 INR | ✅ 340.00 | ✅ 340.00 |

## Misses

- **deepseek-vision** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **deepseek-vision** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-06-28`, expected `2024-10-28`
- **deepseek-vision** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-vision** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-vision** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `100013`, expected `1000013`
- **openai-vision** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2021-10-29`, expected `2024-10-28`; total: got `7926.00`, expected `7226.00`
- **openai-vision** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-29`, expected `2016-01-27`
