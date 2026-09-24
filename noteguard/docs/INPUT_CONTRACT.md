# Input contract and synthetic scenarios

## What is inspected

Individual clinical records and reports for one synthetic encounter, not a complete case-report essay and not an assumed complete hospital record. Required source fields: namespace, source ID, positive integer version, source timestamp, author/owner, discipline, patient and encounter. The demonstrator fixes the encounter and assigns patient context from it; the operator must verify that imported material belongs to that encounter. It does not infer identity from PDF content.

Disciplines: clinician, nursing, pharmacy, physiotherapy, counselling/social work, other. Each has a synthetic team member. Scope and authorship are illustrative; importing on behalf of an author is not proof of that author's identity or signature.

Text: max 200,000 characters, nonempty. PDF: max 10 MB; up to 50 pages of extraction. Over-limit-page-count, malformed/encrypted extraction failures retain the attachment for manual review rather than reporting success. Empty/selectable-text-poor pages (<30 nonwhitespace characters) are marked needs_review; mixed documents are partial. This heuristic can miss an unread image on an otherwise text-rich page. Every extracted PDF must be compared with the original. OCR is not run.

## Bounded English recognition

Assertions should appear one per line. Matching is case-insensitive; evidence always cites original characters. Unrecognised text remains readable but may produce no flag. No flag does not mean complete/safe documentation.

| Family | Recognised examples | Important boundary |
|---|---|---|
| Potassium | `Potassium 6.4 mmol/L`, `K+ 6.4 mmol/L` | Demo threshold >=6.4 from acceptance brief, no clinical calibration |
| Response | `Potassium reviewed`, `Potassium treated`, `Potassium repeated` | Later clinician source only; conservative negation/conditional/planned terms reject suppression |
| Allergy | `NKDA`, `No known drug allergies`, `Allergy: penicillin`, `Penicillin allergy` | Only this named allergy is supported; no general allergy NLP |
| Reconciliation | `Allergy reconciled: penicillin allergy confirmed` or `Allergy reconciled: NKDA confirmed` | Must be a later clinician source; no automatic resolution of existing Tier 1 |
| Dose | `Amlodipine 5 mg oral daily` | amlodipine/lisinopril/metformin, mg, oral, daily/twice daily; other units/routes/schedules require manual review |
| Dose change | `Amlodipine dose changed from 5 mg to 10 mg oral daily` | Must match both doses, frequency, timing and clinician authorship |
| Pending | `Pending blood culture result` | blood culture/culture/blood test/ECG; one related action line |
| Follow-up | `Follow-up for blood culture result; owner: lee; due: 2026-09-23T14:00:00+08:00` | Exact team ID and ISO date with timezone; deadline after source time |
| ECG | `ECG performed`, `ECG completed` | Negated/planned statements do not prove performance |
| Revision | Same source ID, higher version | Full old/new text shown. Repeated version content is a question, not proof of unsafe copying |

The engine has no specimen-level identity or broad temporal semantic reasoning. Multiple measurements, implicit drug changes, indirect references and complex negation require manual review. This is a transparent bounded checker, not clinical NLP validation.

## Synthetic fixture

All names, records and PDFs were authored for this application. No real patient record or public clinical dataset was imported.

| Source | Time (SGT, 22 Sep 2026) | Expected result |
|---|---|---|
| medical | 09:00 | NKDA and amlodipine 5 mg provide comparison evidence |
| nursing | 10:00 | Potassium 6.4 and penicillin allergy: Tier 1 response and allergy questions |
| pharmacy | 10:15 | Amlodipine 10 mg: Tier 2 dose question, pharmacy involved |
| physio | 10:30 | Mobility statement retained; no invented contradiction |
| social | 10:45 | Support/transport statement retained; no invented risk |
| followup | 11:00 | Pending culture without owner/deadline: Tier 2 |
| response (optional) | 13:00 | Explicit review, allergy clarification, dose change, follow-up and ECG; old issue applicability changes but human disposition remains required |
| selectable-report.pdf | Operator supplies time | Readable laboratory text, source/page offsets available |
| scanned-report.pdf | Operator supplies time | No selectable text; original retained, Tier 2 manual review |
| partial-report.pdf | Operator supplies time | First page readable, second scanned; Tier 2 manual review of page 2 |

Tests add negative/control cases: negation, earlier response, wrong discipline, wrong dose change, owner without deadline, deadline without owner, expired deadline, unknown owner, normal source revision and exact repeated version. No broad-language accuracy claim is made.
