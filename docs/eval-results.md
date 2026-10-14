# Model comparison on the sample bills

**Not run yet.** No GLM or DeepSeek API key was available in the build environment, so there are no live accuracy numbers.

To run the comparison once the keys are set:

```bash
bill-reader models check
bill-reader eval samples/ --models glm-vision,glm-vision-flash,deepseek-vision
```

The command overwrites this file with:
- accuracy per field for each model profile;
- the total each model read on every sample;
- latency, token use and estimated cost;
- a list of misses.

Acceptance targets from the spec:
- **AC-4:** total correct on ≥4 of 5 samples, and supplier name recognisably correct on ≥4 of 5.
- **AC-5:** sample 02 reads subtotal 2,305,000.00, VAT 414,900.00 and total 2,719,900.00.
- **AC-8:** account code matches the expected one on ≥4 of 5 samples.
