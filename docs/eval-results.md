# Model comparison on the sample bills

Generated 2026-10-19 05:13 UTC by `bill-reader eval`. Account codes suggested by the `deepseek-text` profile in every run.

## Accuracy per field

| Profile | Model | Mode | supplier_name | bill_number | bill_date | total | vat_amount | currency | account_code | Mean latency | Tokens in/out | Est. cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek-vision | deepseek-flash | vision | 3/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 15296 ms | 26676/18847 | $0.0279 |
| openai-vision | gpt-4.1 | vision | 5/5 | 4/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 4107 ms | 18620/3506 | – |
| openai-gpt-5.4-mini | gpt-5.4-mini | vision | 4/5 | 4/5 | 2/4 | 4/5 | 1/1 | 5/5 | 3/5 | 3705 ms | 18559/3462 | – |
| openai-gpt-5.5 | gpt-5.5 | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 11430 ms | 18559/5698 | – |
| openai-gpt-5.6-terra | gpt-5.6-terra | vision | 5/5 | 4/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 12028 ms | 26144/6997 | – |
| openai-gpt-5.6-luna | gpt-5.6-luna | vision | 5/5 | 3/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 17205 ms | 26144/9728 | – |
| openai-gpt-5.6-sol | gpt-5.6-sol | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 25791 ms | 26144/10255 | – |
| openai-gpt-6-astra | gpt-6-astra | vision | 5/5 | 5/5 | 2/4 | 5/5 | 1/1 | 5/5 | 4/5 | 30630 ms | 26144/8224 | – |
| openai-gpt-6-luna | gpt-6-luna | vision | 5/5 | 5/5 | 2/4 | 3/5 | 1/1 | 5/5 | 4/5 | 25011 ms | 26144/14937 | – |
| openai-gpt-6-sol | gpt-6-sol | vision | 5/5 | 5/5 | 2/4 | 4/5 | 1/1 | 5/5 | 4/5 | 16410 ms | 26144/8501 | – |
| openai-gpt-6.1-sol | gpt-6.1-sol | vision | 5/5 | 5/5 | 2/4 | 4/5 | 1/1 | 5/5 | 3/5 | 36158 ms | 26144/7620 | – |

## Total read per sample

| Sample | Expected | deepseek-vision | openai-vision | openai-gpt-5.4-mini | openai-gpt-5.5 | openai-gpt-5.6-terra | openai-gpt-5.6-luna | openai-gpt-5.6-sol | openai-gpt-6-astra | openai-gpt-6-luna | openai-gpt-6-sol | openai-gpt-6.1-sol |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 01-saman-motors-si-handwritten.jpg | 44800.00 LKR | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ✅ 44800.00 | ❌ 144800.00 | ✅ 44800.00 | ✅ 44800.00 |
| 02-vat-company-en-printed-tax-invoice.png | 2719900.00 LKR | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 | ✅ 2719900.00 |
| 03-malindu-spice-hut-si-thermal.png | 510.00 LKR | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 | ✅ 510.00 |
| 04-samsuddin-siddiqui-en-handwritten-inr.png | 7226.00 INR | ✅ 7226.00 | ❌ 7926.00 | ❌ 9726.00 | ✅ 7226.00 | ❌ 5226.00 | ❌ 7276.00 | ✅ 7226.00 | ✅ 7226.00 | ❌ 5126.00 | ❌ 7220.00 | ❌ 7220.00 |
| 05-sea-rock-restaurant-en-handwritten-inr.png | 340.00 INR | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 | ✅ 340.00 |

## Misses

- **deepseek-vision** · 01-saman-motors-si-handwritten.jpg: supplier_name: got `Seven Motors (Pvt) Ltd`, expected `Saman Motors`
- **deepseek-vision** · 02-vat-company-en-printed-tax-invoice.png: supplier_name: got `VCom Company (Pvt) Ltd`, expected `Vat Company (Pvt) Ltd`; account_code: got `6-2220`, expected `5-1000`
- **deepseek-vision** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-06-28`, expected `2024-10-28`
- **deepseek-vision** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-vision** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-vision** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `100013`, expected `1000013`
- **openai-vision** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2021-10-29`, expected `2024-10-28`; total: got `7926.00`, expected `7226.00`
- **openai-vision** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-29`, expected `2016-01-27`
- **openai-gpt-5.4-mini** · 01-saman-motors-si-handwritten.jpg: supplier_name: got `Samas Motorers Hero`, expected `Saman Motors`
- **openai-gpt-5.4-mini** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.4-mini** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `100013`, expected `1000013`; account_code: got `5-1000`, expected `6-3110`
- **openai-gpt-5.4-mini** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-09-28`, expected `2024-10-28`; total: got `9726.00`, expected `7226.00`
- **openai-gpt-5.4-mini** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-07-21`, expected `2016-01-27`
- **openai-gpt-5.5** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.5** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-29`, expected `2024-10-28`
- **openai-gpt-5.5** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2006-11-24`, expected `2016-01-27`
- **openai-gpt-5.6-terra** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.6-terra** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `61`, expected `1000013`
- **openai-gpt-5.6-terra** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2026-03-14`, expected `2024-10-28`; total: got `5226.00`, expected `7226.00`
- **openai-gpt-5.6-terra** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-gpt-5.6-luna** · 01-saman-motors-si-handwritten.jpg: bill_number: got `None`, expected `8502`
- **openai-gpt-5.6-luna** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.6-luna** · 03-malindu-spice-hut-si-thermal.png: bill_number: got `100013`, expected `1000013`
- **openai-gpt-5.6-luna** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2023-12-30`, expected `2024-10-28`; total: got `7276.00`, expected `7226.00`
- **openai-gpt-5.6-luna** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-24`, expected `2016-01-27`
- **openai-gpt-5.6-sol** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-5.6-sol** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-29`, expected `2024-10-28`
- **openai-gpt-5.6-sol** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-gpt-6-astra** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-astra** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-23`, expected `2024-10-28`
- **openai-gpt-6-astra** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
- **openai-gpt-6-luna** · 01-saman-motors-si-handwritten.jpg: total: got `144800.00`, expected `44800.00`
- **openai-gpt-6-luna** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-luna** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-23`, expected `2024-10-28`; total: got `5126.00`, expected `7226.00`
- **openai-gpt-6-luna** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-21`, expected `2016-01-27`
- **openai-gpt-6-sol** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6-sol** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-29`, expected `2024-10-28`; total: got `7220.00`, expected `7226.00`
- **openai-gpt-6-sol** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2026-11-27`, expected `2016-01-27`
- **openai-gpt-6.1-sol** · 02-vat-company-en-printed-tax-invoice.png: account_code: got `6-9999`, expected `5-1000`
- **openai-gpt-6.1-sol** · 03-malindu-spice-hut-si-thermal.png: account_code: got `5-1000`, expected `6-3110`
- **openai-gpt-6.1-sol** · 04-samsuddin-siddiqui-en-handwritten-inr.png: bill_date: got `2024-10-23`, expected `2024-10-28`; total: got `7220.00`, expected `7226.00`
- **openai-gpt-6.1-sol** · 05-sea-rock-restaurant-en-handwritten-inr.png: bill_date: got `2016-11-27`, expected `2016-01-27`
