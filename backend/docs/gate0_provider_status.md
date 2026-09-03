# Gate 0 — Provider Protocol Smoke Check (M4)

Minimal, non-clinical, no-PHI smoke check of the DeepSeek Provider path.

```text
provider:          deepseek (OpenAI-compatible endpoint)
endpoint:          https://api.deepseek.com/chat/completions
request protocol:  Chat Completions API over httpx
thinking:          enabled
generated limit:   omitted
model:             deepseek-v4-flash (probe); deepseek-v4-pro available
output:            final message.content only (reasoning_content is ignored)
timeout:           n/a (single probe)
result:            LIVE_VERIFIED (2026-08-26)
```

Details:

- The key is read from the environment (DEEPSEEK_API_KEY, then Natingale_API_KEY).
  The probe read it from the Windows User-level environment variable
  `Natingale_API_KEY` (sk-…). The key is never printed or stored.
- A minimal non-clinical, no-PHI prompt (`Reply with the single word: OK`) returned
  `OK` with usage input=90 / output=4, confirming the original Provider path.

Protocol update (2026-09-03): the adapter moved from Anthropic Messages to
DeepSeek Chat Completions after live multilingual calls exhausted the required
Anthropic `max_tokens` budget in thinking before final output. The current
request sends the requirements plus de-identified text, keeps thinking enabled,
omits `max_tokens`, requests JSON output for structured flows, waits for the
completed response, and parses only final `message.content`. A live synthetic
multilingual rerun returned a summary plus 4/4 exactly anchored candidates.
