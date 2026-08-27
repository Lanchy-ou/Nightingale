# E4 Task Card — Local Ambient Voice Capture Adapter

> Status: IMPLEMENTED_WITH_LIMITS

## Outcome

Provide a default-off, local-only Voice lifecycle for patient, Nurse, and Doctor contexts with immutable audio, human speaker review, and exact transcript provenance.

## Permanent contract

- NANTINGALE_VOICE_ENABLED=false by default.
- Product Provider is pinned Systran/faster-whisper-base, CPU int8, local_files_only=True.
- Mock ASR is test-only and never exposed as product capability.
- PyAV validates and decodes WAV/WebM/Ogg in memory.
- Limits: one audio stream, 8 MiB, 120 seconds, 1–2 channels, sane sample rate.
- Original bytes are immutable SQLCipher BLOBs included in encrypted backup/restore.
- Audio never enters LLMClient, logs, or E3 compression.
- The adapter performs no diarization and invents no confidence.
- Every machine segment begins with unknown speaker and requires role-bounded human review before confirmation.
- Patient/role/session changes stop streams, abort requests, revoke object URLs, and clear drafts.

## Current evidence

Historical dated evidence observed one synthetic local ASR slice. The current final environment lacks the ignored model/audio paths, so two real-local-ASR tests are explicitly skipped. Physical microphone capture, noisy/code-switching accuracy, clinical accuracy, and production throughput are not claimed.

## Exit evidence

All key-free Voice lifecycle/RBAC/schema/review/backup contracts pass; current status remains implemented with limits rather than a fresh full ASR rerun.
