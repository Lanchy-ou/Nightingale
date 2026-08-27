# M5 Task Card — Longitudinal Synthetic Demo Data

> Status: COMPLETE

## Outcome

Provide one deep synthetic patient story across 2025–2026 instead of many shallow records.

## Canonical story

Historical headache review and medication review lead into a 2026 pre-consult, Nurse Consult, Doctor Consult, patient follow-up, and clinician review. The story contains worsening headache frequency, nausea, elevated blood pressure, a blood-test action, later improvement, and continued follow-up.

## Permanent contract

- Data is hand-authored synthetic material in backend/seed/fixture.py.
- Facts remain internally consistent.
- Cross-event entity keys are recomputed, not hand-filled.
- Event chronology uses started_at.
- Synthea was not adopted.

## Exit evidence

Seed-integrity, longitudinal scoring, Timeline, Glance, Patient View, and provenance tests use the same canonical story.
