# Learnings: bill-reader-myob-vouchers

Build learnings, spec gaps, and patterns discovered.

**Categories:** spec_gap | design_gap | pattern | best_practice | agent_issue

---

## [L1] spec_gap — No API keys in build env: AC-4/5/8/14-16 live accuracy no...

**When:** 2026-10-14 18:15 UTC
**Category:** spec_gap
**Priority:** high
**Status:** pending

### Detail
No API keys in build env: AC-4/5/8/14-16 live accuracy not verified; eval harness ready

### Action
Run bill-reader eval with ZAI/DeepSeek keys before /specclaw:verify

---

## [L2] design_gap — surya-ocr 0.22 is now a VLM needing vLLM/llama.cpp backen...

**When:** 2026-10-14 18:15 UTC
**Category:** design_gap
**Priority:** medium
**Status:** pending

### Detail
surya-ocr 0.22 is now a VLM needing vLLM/llama.cpp backend and pins pillow<11; adapter only tested with mocks

### Action
Validate Surya install on target machine or pin an older Surya

---

## [L3] design_gap — Files modified outside declared task scope: bill_reader/a...

**When:** 2026-10-14 18:15 UTC
**Category:** design_gap
**Priority:** low
**Status:** pending

### Detail
Files modified outside declared task scope: bill_reader/app.py (T8 web router), bill_reader/llm/profiles.py (T7 active-model overrides), pyproject.toml (T9/T11)

### Action
Declare integration files in tasks

---

## [L4] pattern — Task ID 'T1b' was rejected by specclaw-parse-tasks; IDs m...

**When:** 2026-10-14 18:15 UTC
**Category:** pattern
**Priority:** low
**Status:** pending

### Detail
Task ID 'T1b' was rejected by specclaw-parse-tasks; IDs must be T<number>

### Action
Use numeric task IDs only

---

## [L5] pattern — Recent anthropic SDK uses httpx2; MockTransport tests mus...

**When:** 2026-10-14 18:15 UTC
**Category:** pattern
**Priority:** medium
**Status:** pending

### Detail
Recent anthropic SDK uses httpx2; MockTransport tests must use httpx2 for the Anthropic adapter

### Action
Keep transport lib aligned with SDK

---
