# D4 frozen Copilot eval

Run from `backend/`:

```powershell
.venv/Scripts/python.exe -B scripts/evaluate_copilot.py
```

The runner seeds the canonical synthetic journey in a temporary database and
uses `mock` only. It locks all four query categories to expected
Event/Artifact/quote/exact-span tuples, checks full-history retrieval and
unrelated-span exclusion, rejects AI-summary self-citation and a forged draft
confirmation token, and verifies clinician-selected draft type authority.

Latency is reported separately as `COPILOT_READ_PATH` P50/P95/max with
`glance_latency_included: false`; it must never be presented as Glance P95.

Provider report:

- `mock`: evaluated locally by the command above; it is deterministic and
  makes no network call.
- deterministic fallback: `NOT_APPLICABLE`. D4 deliberately does not turn a
  failed provider into a clinical answer; failure returns explicit
  `unavailable` with no claims or draft. This behavior is covered by
  `tests/test_copilot_evidence.py`.
- `deepseek` live: `NOT_RUN`. A key-free evaluation must not fabricate a live
  provider result. The adapter remains behind the same `LLMClient` redaction
  boundary and its output is independently evidence-validated before display.
