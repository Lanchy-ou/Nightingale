# Architecture, governance and production boundary

```text
Browser tab (clinical data boundary)
  Pasted text / PDF bytes
       -> validated source metadata
       -> immutable source version + SHA-256
       -> PDF.js text/page extraction + local canvas
       -> cutoff/version selection and bounded English checks
       -> flags + exact evidence + owner + rule version
       -> human decision history
       -> source-bounded questions / summary / explicit export
       -> session-only aggregate feedback

Static host: public application assets only, no clinical API
External model: none
Persistent clinical database/cache: none
```

## Domain interface

`source(input)` validates and hashes provenance; `addSource` rejects version reuse with changed metadata/content. `evaluate(sources, cutoff)` returns deterministic candidates. `reconcile(previous, candidates)` preserves decisions and updates current applicability. `decide` requires a permitted demo role, owner and rationale. `resolve` verifies exact original quote offsets. `summary` and `answerQuestion` expose evidence and cutoff. These are internal JavaScript interfaces, not authenticated APIs.

The source holds original-time/import-time, namespace/ID/version, encounter/patient, discipline/owner, source checksum, text checksum, text, page spans and extraction status. PDF buffers are stored separately in a session Map by version ID. No raw source is edited. A repeated import is idempotent. Sources past the cutoff cannot affect checks. Old issue evidence remains linked to the old version even when a newer one changes the assertion.

Unresolved Tier 1 means open, accepted or edited. A check no longer firing changes `current`, not lifecycle status. A human can resolve/dismiss/reopen or explicitly supersede an obsolete concern; current concerns cannot be superseded. Declining a false positive is a recorded disposition, not deletion of evidence. Source-owner defaults are overridden for Tier 1 clinical responsibility and cross-source conflicts. Pharmacy participation is visible but no notification is delivered.

## Demo security and scope

No backend or real login exists. `canAccess` and `canDecide` model roles and encounter scope for testing only. All in-memory state is inspectable/bypassable by the operator. Changing identity clears clinical state and pending inputs. Quality view exposes counts, but this does not establish production aggregate authorisation. The acceptance appendix allows this explicitly labelled browser-memory exception. Production access test is NOT IMPLEMENTED, not PASS.

Local content is never sent to a server/model. Requests are static assets, same-origin worker and service-worker code. Cache-Control is private/no-store; no browser storage or clinical service-worker cache is used. A user-triggered summary download is an explicit export. Browser/OS memory, screenshots, user exports, extensions and endpoint security are outside the privacy guarantee; no forensic erasure claim is made.

PDF.js processes untrusted syntax locally with eval disabled; no PDF scripting is run. Original pages are rendered to canvas; failure is explicit. Size/page bounds reduce accidental overload but do not replace production malware scanning and worker isolation. Text-rich pages may still contain unextracted image content; manual verification remains necessary.

Metadata-only audit entries contain allowlisted actor/action/outcome/time and are session-only. Rich decisions and rationales are separate clinical data. Neither audit hashing nor tamper-resistant persistence is claimed. Redaction operates on a derived copy with mapping; no external egress is currently present. No clinical content goes to console/application logs.

## Production integration design (not implemented)

Authenticate with SMART App Launch / approved OIDC. Enforce clinic + encounter/care-team membership server-side for every direct object and decision; note authorship is not blanket access, and admin is not a clinical superuser. Use approved encrypted storage, TLS, private/no-store responses and short-lived document access. A durable append-only/tamper-evident audit stream records permitted metadata separately from protected clinical decision content.

FHIR R4 mapping: Patient/Encounter identify context; CareTeam/PractitionerRole authorise membership; DocumentReference/Composition/Binary identify source documents; Observation/DiagnosticReport/MedicationRequest/AllergyIntolerance provide structured assertions; Provenance/AuditEvent preserve lineage. Preserve namespace, source ID, version, checksum and idempotency. HL7 v2, CDA/XDS and file adapters normalise into the same contract. Read-only baseline; any write-back is a separate human-authorised reconciliation artifact, amendment or Task.

Future audio extension fields: `audio_asset_id`, `transcript_id`, `transcript_version`, `speaker_label`, `start_ms`, `end_ms`, `transcription_confidence`, `consent_status`. Source objects currently have `audio: null`; no voice subsystem exists.

## Governed improvement

Session decisions record acceptance, dismissal, edits, owner changes, rationale and usefulness categories. Aggregate counts are not estimates of sensitivity, specificity, clinical usefulness or missed concerns. A pilot needs clinician-labelled adjudication and timestamps to measure actionability, false positives, missed concerns, owner response time and disposition.

Feedback can propose dictionary/rule/ranking/question changes. Every proposal requires a version, held-out offline evaluation, clinical approval, monitored release and rollback. There is no live self-modification. Medical Director, Quality/Risk and Legal production reports must require specific authority and expose only PHI-minimised aggregate risk and rule metrics.
