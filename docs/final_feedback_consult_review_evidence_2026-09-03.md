# F Final Consult Review — Completion Evidence

Date: 2026-09-03
Result: `IMPLEMENTED_WITH_LIMITS`
Data boundary: hand-written synthetic data only

## Delivered behavior

- Manual Doctor Consult creation requires three literal-true fields:
  `speaker_labels_reviewed`, `mixed_language_content_reviewed`, and
  `medication_dosage_mentions_reviewed`.
- Doctor Voice confirmation applies the same server-side gate. Nurse and
  patient Voice confirmation bodies do not require the clinician-only fields.
- Missing or false fields return 422 before Doctor Consult downstream AI work.
  Manual rejection creates no Event or Transcript; Voice rejection leaves the
  existing capture in `needs_review` with no Event or confirmed Transcript.
- The accepted path still commits the immutable Transcript before the existing
  redaction/Provider/fallback/provenance pipeline. Stable operation identities
  keep retries idempotent.
- `doctor_consult_create` and Doctor `voice_confirm` Audit rows identify the
  reviewer, role and time in the existing Audit columns and contain exactly the
  three booleans in `details`. Transcript text, patient identifiers,
  medication and dosage text are absent from those details.
- Both manual and Doctor Voice UIs show all three checkboxes. Confirmation is
  disabled until all are selected, and any transcript/speaker edit clears the
  current acknowledgement. The server remains authoritative.

## Frozen mixed-language result

The repository fixture contains one Doctor/Patient consultation with a single
Malay-English-Hokkien patient statement. It reuses only the canonical headache,
nausea, blood-test and propranolol facts.

| Evidence path | Observed result | Claim boundary |
| --- | --- | --- |
| UTF-8/canonical Transcript | Exact round-trip; continuous indexes and reviewed `doctor|patient` labels preserved | Transport and human review only |
| Mock | Exact quote resolved to the immutable Transcript Artifact and segment Span | Deterministic provenance mechanics only |
| Changed/nonexistent quote | Provider candidate dropped; controlled deterministic fallback used | No fuzzy or manufactured source |
| Deterministic fallback | Preserved source wording and produced only source-supported English-keyword symptom output in the unsupported-language test | No translation or multilingual clinical understanding claim |
| Unknown speaker | Preview remained `NEEDS_REVIEW`; canonical submission rejected until a human assigned an allowed role | No automatic attribution/diarization claim |
| Live external Provider multilingual evaluation | After the protocol revision, DeepSeek returned a complete summary and 4 candidates; all 4 quotes anchored exactly | Contract/provenance pass on one synthetic case, not clinical validation |
| Historical Provider failure path | The earlier Anthropic-format calls exhausted the required token budget in thinking; invalid output triggered `deterministic_fallback` with 2 exactly sourced highlights | No partial Provider result was persisted |
| Real local ASR input tests | 2 passed with the pinned local `Systran/faster-whisper-base` model and an ignored synthetic WAV | Local transcription mechanics passed; accuracy remains limited |

Medication/dosage review means comparison with the source Transcript by the
clinician. No RxNorm, MIMS, BNF or other external medical-reference validation
was added.

## Verification observed

- New F Final module: `9 passed`.
- Focused provenance, RBAC clinic scope, publication and concurrency group:
  `75 passed`.
- Focused SL1/SL2/SL3/Shadow isolation group: `62 passed`, `650 deselected`.
- Full backend after Provider revision: `714 collected`, `712 passed`, `2 skipped`.
- Frontend production build: passed; `112 modules transformed`.
- TypeScript no-emit compile: passed.
- Frontend transcript-range, Voice-capture and Patient Check-in Node checks:
  passed.
- `git diff --check`: passed.
- Secret scan: `SECRET_SCAN_PASS`.

### Approved live/local follow-up (2026-09-03)

- A locally generated 17.95-second synthetic WAV produced 3 non-empty,
  timestamped segments. Language was detected as English and every speaker
  remained explicitly `unknown_speaker`, as required before human review.
- The ASR preserved `3 out of 10`, `nausea`, `propranolol 20 milligrams`, and
  `blood test`. It misrecognized `Sakit kepala` as `Socket coupler` and
  `masih ada` as `must aid`. This is a concrete Base-model/code-switching
  limitation, not a multilingual accuracy pass.
- Two direct DeepSeek multilingual calls were schema-rejected: the first text
  response contained truncated JSON and the second had no extractable text
  block. A metadata-only reproduction confirmed the cause: DeepSeek returned
  `stop_reason=max_tokens`, used all 2,000 output tokens in a `ThinkingBlock`,
  and emitted no `TextBlock` for the adapter to parse. A subsequent call through
  the production Doctor Consult endpoint
  completed with `generation_method=deterministic_fallback`,
  `fallback_reason=invalid_output`, 2 source-supported highlights, and working
  provenance.
- The adapter was then moved to DeepSeek Chat Completions. It now sends the
  requirements plus de-identified text, keeps thinking enabled, sends no
  `max_tokens` or `max_output_tokens`, waits for completion, ignores
  `reasoning_content`, and validates only final `message.content`. The same live
  synthetic multilingual input then returned a complete summary plus 4
  candidates (`symptom`, `symptom`, `medication`, `task`); all 4 quotes resolved
  exactly to source spans.
- The focused redaction, extraction, invalid-output/timeout fallback,
  provenance, consult-review, and revised Provider contract group passed:
  `41 passed`.

Pytest emitted an environment-only cache/temporary-directory permission warning
after the successful run. The process exit code was 0; no test was converted
to a pass or skip because of that warning.

## Release boundary

The consult review slice is verified as an engineering control with synthetic
data. It does not establish automatic speaker attribution, multilingual
clinical extraction, translation, medication validity, physical-microphone
accuracy, noisy-clinic performance or production medical safety.

The current Self-Learning architecture and its non-promotion boundary are
documented separately in
`docs/self_learning_design_and_release_boundary_2026-09-03.md`. Formal Glance
remains deterministic `base_only`; no real-feedback model was trained,
promoted, deployed or served.
