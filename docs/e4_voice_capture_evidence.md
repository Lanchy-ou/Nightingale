# E4 Local Voice Capture Evidence — 2026-08-28

## Result

E4 reached a real local synthetic vertical slice, not a mock-only prototype:

```text
browser WAV/WebM/Ogg intent
-> immutable encrypted Recording BLOB
-> faster-whisper multilingual Base on local CPU
-> timestamped machine segments with unknown speaker
-> explicit human review
-> immutable canonical Transcript
-> existing redaction / LLMClient / fallback / exact-provenance pipeline
```

`NANTINGALE_VOICE_ENABLED=false` remains the default. Product UI appears only
when the flag is enabled, the authenticated role has an allowed capture mode,
the provider is `faster_whisper`, and the pre-downloaded model directory is
ready. Mock remains an automated-test adapter and never exposes product UI.

## Gate 0 observation

| Item | Observed value |
|---|---|
| Python | 3.13.5 |
| faster-whisper | 1.2.1 |
| CTranslate2 | 4.8.1 |
| PyAV | 18.1.0 |
| Model | `Systran/faster-whisper-base` multilingual |
| Revision | `a80717a3a48b1b28aa687bca146cb7301feae1b1` |
| Device / compute | CPU / int8 |
| Synthetic WAV SHA-256 | `b999bd2e8daaca659b975ea5fa2044e9280fe0c03443710a2d712bd65313d9fc` |
| Duration | 14.470 s |
| Project-venv latency | 1.565 s |
| Output | 2 non-empty timestamped segments |
| Speaker / confidence | `null` / `null`; `unknown_speaker` visible |

The smoke ran with `HF_HUB_OFFLINE=1` and a local directory. Latency includes
local model loading on this machine and is reported separately from Glance P95;
it is not production capacity or an accuracy score. The speech was generated
locally from an authored synthetic sentence and contains no real patient data.

Reproduction:

```powershell
cd backend
.venv/Scripts/python.exe scripts/prepare_local_asr.py
$env:HF_HUB_OFFLINE='1'
.venv/Scripts/python.exe scripts/smoke_local_asr.py <synthetic.wav> --model-dir .models/faster-whisper-base
```

## Safety and product evidence

- Server DB identity selects `doctor_consult`, `nurse_consult`, or
  `patient_session`; client intent cannot cross role or clinic boundaries.
- PyAV checks actual container bytes, one audio stream, duration, channel count
  and sample rate in memory. WAV/WebM/Ogg pass synthetic container tests;
  mismatched MIME, corrupt content and limits fail before persistence.
- Original audio, machine transcript and confirmed transcript remain separate.
  Raw audio never enters the Summary LLM and no provider raw response is stored.
- Local ASR performs no diarization. Every observed segment enters review with
  `speaker_candidate=null`, `confidence=null` and `unknown_speaker`; confirmation
  requires a permitted role-specific speaker and explicit issue resolution.
- Voice-created Transcript/Highlight rows retain E2 score composition. E3 can
  create and restore a cold shadow copy of an old voice Transcript while exact
  Transcript spans and audio-range pointers continue to resolve. The Recording
  BLOB stays separate and encrypted; E3 does not compress it.
- SQLCipher backup/restore tests assert both E3 archive bytes and E4 recording
  bytes survive under the rotated key.

## Verification

- Backend: **482 passed** with explicit ignored Base model and synthetic WAV;
  both real local-ASR integration tests ran rather than skipped.
- Security/integration: **20 passed**.
- D3 corpus validation/runtime: PASS; live LLM provider remains `NOT_RUN`.
- D4 frozen Copilot evaluation: PASS.
- Frontend state tests: 2 passed; production build PASS.
- Browser: Clinician, Nurse and Patient entries observed; role switch cleared
  consent/state; console contained 0 warnings/errors.
- Dependency, secret, Caddy and diff checks: PASS.

The physical microphone was not activated during automated browser QA because
the repository contract permits synthetic data only and the test host could
capture uncontrolled ambient speech. This is reported as not exercised, not
replaced by a fabricated browser recording claim. Real acoustic recognition and
the full server journey were instead exercised with the fixed synthetic WAV.

## Non-claims

No evidence here establishes production medical suitability, human usability,
clinical accuracy, diarization, noisy/overlap/code-switching performance,
multi-device capture, external ASR privacy, or production throughput.
