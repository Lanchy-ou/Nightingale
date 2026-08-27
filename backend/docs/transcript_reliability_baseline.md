# D3 Transcript Reliability Baseline

```text
CORPUS_VALIDATION_PASS
FROZEN_CORPUS
LOCAL_DETERMINISTIC_RUNTIME_EVALUATED
PROVIDER_LAYER_NOT_RUN
```

## Scope and lineage

D3 implements raw text normalization preview, user review, canonical confirmation through the existing C1 doctor-consult endpoint, and a reproducible frozen evaluation. It does not add audio, ASR, OCR, EHR import, speaker guessing, a second provider exit, or model training.

- D2 review-fixed integration base: `2f71bdd70248303b8963bd34a25a536b4f98e604`.
- Corpus preparation base: `ca114ebf6a2a92155aa6a1d6f9e48b934c76b528`.
- Frozen normalizer SHA-256 before the first holdout run: `1ac0e01e92401b1728e7b938541e71f8d95e81cca137376004953eb2cd371476`.
- Corpus data classification: `SYNTHETIC_ONLY`; no external dataset or real PHI.
- The frozen holdout was evaluated once after freezing the normalizer. No outcome-dependent rule change was made afterward.

## Corpus and integrity

- Total cases: 40.
- Development: 26.
- Frozen holdout: 14.
- Expected normalize outcomes: 32 `ACCEPT`, 5 `NEEDS_REVIEW`, 3 `REJECT`.
- Encoding: UTF-8 without BOM, LF newlines, final LF.
- Protocol limits: 4096 raw-text bytes, 500 segments, 4000 characters per segment.
- Manifest byte length: 11,110.
- Manifest SHA-256: `35924adc9e13d83432d16220b32cbd06be42aa813e75de00f3735666b39f26b5`.
- Frozen holdout composite SHA-256: `e2b429ff98cfc802b307c7de46f4ffa0006e12211cce7efaf37799b762a4d962`.
- Composite input: sorted `path<TAB>byte_length<TAB>sha256<LF>` rows.
- Validation: 40/40 byte lengths and case hashes verified; declared and actual case sets matched; holdout digest reproduced.

Coverage includes canonical/case-variant/Dr-Pt labels, continuation, blank and repeated labels, unknown/third-party/unlabelled speakers, Chinese-English content, self-correction, interruption, medication/dose, negation, time and task status, contradiction, low-information and overlong input, synthetic name/ID/phone, prompt injection, malicious JSON/Markdown, anchorable/unanchorable quotes, and provider invalid-schema/failure/fallback annotations.

UNKNOWN is never converted to doctor, patient, zero, false, or another default.

## Normalize results

| Split | Outcome accuracy | Speaker mapping | Ambiguous/unsupported correctly blocked |
|---|---:|---:|---:|
| development | 26/26 = 1.000000 | 55/55 = 1.000000 | N/A |
| frozen_holdout | 14/14 = 1.000000 | 12/12 = 1.000000 | 8/8 = 1.000000 |

Hard-gate observations from the frozen runner:

- silent speaker invention: 0;
- silent truncation: 0;
- known synthetic PHI left unredacted in local provider-bound payload construction: 0/5 expectations;
- deterministic fallback candidates without an exact source anchor: 0.

Integration tests separately establish:

- raw source overwritten: 0;
- unanchored Highlight persisted: 0;
- unresolved null speaker crossing canonical confirm: 0;
- normalize-time Event/Artifact/Audit writes: 0;
- normalize-time LLM/provider calls: 0.

## Redaction and anchoring

Development annotated exact quote restoration/anchor: 7/7 = 1.000000.

Frozen holdout deliberately unanchorable quotes correctly blocked: 3/3 = 1.000000. The holdout contains no positively annotated anchorable quote, so a positive holdout anchor rate is not invented.

The evaluation reconstructs only local redacted payloads, restores complete placeholders locally, and uses the permanent deterministic `locate_span`/`extract_text` contract. It makes no provider or network call and persists no clinical row.

## Deterministic fallback layer

Provider and fallback are not combined.

Development, exact `(entity_type, source quote)` matching over the explicitly annotated subset:

- evaluated cases: 14;
- fallback candidates: 9;
- exact entity true positives / predicted / gold: 8 / 9 / 14;
- exact entity precision: 0.888889;
- exact entity recall: 0.571429;
- exact task true positives / predicted / gold: 1 / 1 / 2;
- exact task precision: 1.000000;
- exact task recall: 0.500000;
- hallucinated or unanchored fallback candidates: 0.

Frozen holdout fallback annotations contain one explicitly evaluated zero-clinical-information case. It produced 0 candidates as permitted. There are no holdout gold entity/task annotations suitable for precision/recall, so those holdout metrics are `null`, not zero and not merged with development.

These results demonstrate conservative extractive behavior and also document incomplete recall. D3 does not tune fallback rules against the holdout.

## Provider layer

```text
status = NOT_RUN
provider = deepseek (requires env key; not exercised here)
```

The holdout includes five provider failure/schema/placeholder/anchor-drop annotations, but this frozen local evaluation never calls a provider or network. The separately documented Gate 0 smoke check verified the adapter protocol, not corpus quality. Existing integration tests exercise classified fallback reasons with controlled mock/failure clients. No provider corpus accuracy, extraction score, latency, or live reliability is claimed.

## Conflict metric

Corpus conflict flag accuracy is `NOT_EVALUATED`. The standalone transcript corpus intentionally has no authorized patient database or clinician-note comparison context, while the M4 bounded conflict contract compares AI candidates only with clinician-authored records. Fifteen cases carry explicit boolean conflict annotations, including one positive development case, but converting those annotations into a standalone substitute conflict engine would test a different contract.

Existing backend tests continue to cover the bounded clinician-authority conflict behavior. This limitation is explicit and is not reported as a passing score.

## Product workflow verification

The New Consult flow is now:

```text
Paste raw transcript
-> server-side deterministic preview with source ranges
-> Review segments
-> resolve unknown speakers / edit / split / merge
-> Confirm continuous doctor|patient canonical segments
-> existing C1 raw-first Doctor Consult ingestion
-> existing M4 redaction/provider-or-fallback/provenance path
```

Browser QA with synthetic data verified:

- `ACCEPT`, `NEEDS_REVIEW`, and `REJECT` states are visible;
- unknown speaker blocks confirmation until explicitly corrected;
- rejected unlabelled text cannot be confirmed;
- split and merge regenerate continuous indexes;
- confirm creates a new Doctor Consult, saves immutable Transcript first, then produces a separately labelled deterministic fallback summary and one exact-source Highlight;
- patient switching clears the unconfirmed raw draft and disables review in the next patient workspace;
- browser console warnings/errors: 0.

No fake ASR confidence or timestamps are displayed.

## Reproduction

From `backend/`:

```powershell
python scripts/evaluate_transcripts.py --validate-corpus
python scripts/evaluate_transcripts.py --evaluate-runtime
python -m pytest
```

From `frontend/`:

```powershell
npm run build
```

Final gate verification recorded for this worktree:

- corpus validation: exit 0;
- deterministic runtime evaluation: exit 0, hard gates pass;
- backend: 296 passed;
- frontend production build: passed;
- local three-step browser QA: passed.
