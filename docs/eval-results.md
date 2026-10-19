# Model comparison on the sample bills

Generated 2026-10-19 07:45 UTC by `bill-reader eval`. Account codes suggested by the `deepseek-text` profile in every run.

## Accuracy per field

| Profile | Model | Mode | supplier_name | bill_number | bill_date | total | vat_amount | currency | account_code | Mean latency | Tokens in/out | Est. cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-vision | deepseek-flash | vision | 4/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 22248 ms | 32025/24782 | $0.0393 |
| openai-gpt-5.5 | gpt-5.5 | vision | 5/5 | 4/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 15891 ms | 18559/6596 | $0.2907 |
| openai-gpt-5.6-sol | gpt-5.6-sol | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 28092 ms | 26144/10491 | $0.3144 |
| openai-gpt-6-astra | gpt-6-astra | vision | 5/5 | 5/5 | 3/4 | 5/5 | 1/1 | 5/5 | 3/5 | 30404 ms | 26144/7655 | $0.6442 |
| openai-gpt-6-sol | gpt-6-sol | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 18652 ms | 26144/9239 | $0.1447 |
| openai-gpt-6-luna | gpt-6-luna | vision | 5/5 | 5/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 63817 ms | 26144/13695 | $0.0095 |
| openai-gpt-5.4-mini | gpt-5.4-mini | vision | 5/5 | 3/5 | 3/4 | 4/5 | 1/1 | 4/5 | 4/5 | 3776 ms | 18559/3187 | $0.0283 |
| gemini-4-argon | gemini-4-argon | vision | 5/5 | 5/5 | 3/4 | 5/5 | 1/1 | 5/5 | 3/5 | 36649 ms | 29504/5020 | $0.1092 |
| gemini-3.1-pro | gemini-3.1-pro-preview | vision | 1/5 | 1/5 | 1/4 | 1/5 | 0/1 | 1/5 | 0/5 | 162594 ms | 5879/552 | $0.0184 |
| gemini-3.8-flash | gemini-3.8-flash | vision | 5/5 | 5/5 | 3/4 | 5/5 | 1/1 | 5/5 | 3/5 | 17245 ms | 29469/4757 | $0.0399 |
| gemini-3.6-flash | gemini-3.6-flash | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 3/5 | 14898 ms | 29469/4771 | $0.0400 |
| gemini-3.5-flash-lite | gemini-3.5-flash-lite | vision | 5/5 | 4/5 | 3/4 | 5/5 | 1/1 | 5/5 | 3/5 | 3097 ms | 29469/3847 | $0.0185 |

## Total read per sample

| Sample | Expected | deepseek-vision | openai-gpt-5.5 | openai-gpt-5.6-sol | openai-gpt-6-astra | openai-gpt-6-sol | openai-gpt-6-luna | openai-gpt-5.4-mini | gemini-4-argon | gemini-3.1-pro | gemini-3.8-flash | gemini-3.6-flash | gemini-3.5-flash-lite |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-saman-motors-si-handwritten.jpg | 44800.00 LKR | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ❌ gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out. | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 |
| 02-vat-company-en-printed-tax-invoice.png | 2719900.00 LKR | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ❌ gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out. | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 |
| 03-malindu-spice-hut-si-thermal.png | 510.00 LKR | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 |
| 04-samsuddin-siddiqui-en-handwritten-inr.png | 7226.00 INR | ✅ 7226.00 | ❌ 7126.00 | ✅ 7226.00 | ✅ 7226.00 | ✅ 7226.00 | ❌ 7326.00 | ❌ 3726.00 | ✅ 7226.00 | ❌ gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out. | ✅ 7226.00 | ✅ 7226.00 | ✅ 7226.00 |
| 05-sea-rock-restaurant-en-handwritten-inr.png | 340.00 INR | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ❌ gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out. | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 |

## Misses

- **deepseek-vision** · 02-vat-company-en-printed-tax-invoice.png: supplier_name: got `VCom Company (Pvt) Ltd`, expected `Vat Company (Pvt) Ltd`; account_code: got `6-2220`, expected `5-1000`
- **deepseek-vision** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-06-28`, expected `2024-10-28`
- **deepseek-vision** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-gpt-5.5** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.5** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `100013`, expected `1000013`
- **openai-gpt-5.5** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-23`, expected `2024-10-28`; total: got `7126.00`, expected `7226.00`
- **openai-gpt-5.5** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-24`, expected `2016-01-27`
- **openai-gpt-5.6-sol** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.6-sol** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-29`, expected `2024-10-28`
- **openai-gpt-5.6-sol** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-24`, expected `2016-01-27`
- **openai-gpt-6-astra** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-astra** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **openai-gpt-6-astra** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-gpt-6-sol** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-sol** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-29`, expected `2024-10-28`
- **openai-gpt-6-sol** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-27`, expected `2016-01-27`
- **openai-gpt-6-luna** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-luna** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-23`, expected `2024-10-28`; total: got `7326.00`, expected `7226.00`
- **openai-gpt-6-luna** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-21`, expected `2016-01-27`
- **openai-gpt-5.4-mini** · 01-saman-motors-si-handwritten.jpg: bill_number: got `802`, expected `8502`
- **openai-gpt-5.4-mini** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-3510`, expected `5-1000`
- **openai-gpt-5.4-mini** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `000013`, expected `1000013`
- **openai-gpt-5.4-mini** · 04-samsuddin-siddiqui-en-handwritten-inr.png: total: got `3726.00`, expected `7226.00`; currency: got `LKR`, expected `INR`
- **openai-gpt-5.4-mini** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2011-12-26`, expected `2016-01-27`
- **gemini-4-argon** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **gemini-4-argon** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **gemini-4-argon** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **gemini-3.1-pro** · 01-saman-motors-si-handwritten.jpg: failed: gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out.
- **gemini-3.1-pro** · 02-vat-company-en-printed-tax-invoice.png: failed: gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out.
- **gemini-3.1-pro** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **gemini-3.1-pro** · 04-samsuddin-siddiqui-en-handwritten-inr.png: failed: gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out.
- **gemini-3.1-pro** · 05-sea-rock-restaurant-en-handwritten-inr.png: failed: gemini-3.1-pro: gemini-3.1-pro: APITimeoutError: Request timed out.
- **gemini-3.8-flash** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **gemini-3.8-flash** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **gemini-3.8-flash** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **gemini-3.6-flash** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **gemini-3.6-flash** · 03-malindu-spice-hut-si-thermal.png: bill_date: got `2023-08-13`, expected `2026-08-13`; account_code: got `5-1000`, expected `6-3110`
- **gemini-3.6-flash** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **gemini-3.5-flash-lite** · 01-saman-motors-si-handwritten.jpg: bill_number: got `None`, expected `8502`
- **gemini-3.5-flash-lite** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **gemini-3.5-flash-lite** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **gemini-3.5-flash-lite** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
