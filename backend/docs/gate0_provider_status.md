# Gate 0 — Provider Protocol Smoke Check (M4)

Minimal, non-clinical, no-PHI smoke check of the frozen "DeepSeek via anthropic SDK" path.

```text
provider:          deepseek (anthropic-compatible endpoint)
endpoint/base_url: https://api.deepseek.com/anthropic
request protocol:  Anthropic Messages API
SDK/package:       anthropic (pip-installed for the probe only; NOT in requirements.txt)
model:             deepseek-v4-flash (probe)
timeout:           n/a (single probe)
result:            NOT_LIVE_VERIFIED
```

Details:

- The probe used the environment variable `ANTHROPIC_AUTH_TOKEN` (the pi agent's own
  token, not a project-owned `sk-` DeepSeek key).
- The endpoint returned `401 AuthenticationError — "Your api key: ****d161 is invalid"`.
  The key is invalid for DeepSeek; it is NOT a project API key.
- Per M4 task card §3 / §16: the frozen live-adapter path is therefore STOPPED.
  Mock + deterministic fallback are implemented; the live DeepSeek adapter reads
  its key from the environment but is marked `blocked` / `NOT_LIVE_VERIFIED`.

Decision:

- Do NOT silently switch provider or SDK.
- The project will use the owner's own DeepSeek key via env var when available;
  until then, generation is `mock` or `deterministic_fallback`, never falsely
  claimed as live.

To re-run the probe with a real key (never print it):

```bash
cd backend
.venv/Scripts/python.exe -c "import os; from anthropic import Anthropic; \
c=Anthropic(api_key=os.environ['DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com/anthropic'); \
print(c.messages.create(model='deepseek-v4-flash', max_tokens=16, messages=[{'role':'user','content':'OK'}]))"
```
