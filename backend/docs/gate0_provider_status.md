# Gate 0 — Provider Protocol Smoke Check (M4)

Minimal, non-clinical, no-PHI smoke check of the frozen "DeepSeek via anthropic SDK" path.

```text
provider:          deepseek (anthropic-compatible endpoint)
endpoint/base_url: https://api.deepseek.com/anthropic
request protocol:  Anthropic Messages API
SDK/package:       anthropic 1.x (now a declared dependency in requirements.txt)
model:             deepseek-v4-flash (probe); deepseek-v4-pro available
blocks:            ThinkingBlock + TextBlock (text must be extracted from TextBlock)
timeout:           n/a (single probe)
result:            LIVE_VERIFIED (2026-08-26)
```

Details:

- The key is read from the environment (DEEPSEEK_API_KEY, then Natingale_API_KEY).
  The probe read it from the Windows User-level environment variable
  `Natingale_API_KEY` (sk-…). The key is never printed or stored.
- A minimal non-clinical, no-PHI prompt (`Reply with the single word: OK`) returned
  `OK` with usage input=90 / output=4, confirming the anthropic-SDK → DeepSeek
  path works end-to-end.
- Note: `deepseek-v4-flash` emits a `ThinkingBlock` before the `TextBlock`; the
  adapter extracts only text blocks.
