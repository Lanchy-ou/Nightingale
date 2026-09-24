"""Reproducible synthetic inputs and four-page technical brief. No patient data."""
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output' / 'pdf'
OUT.mkdir(parents=True, exist_ok=True)

def scan(c):
    image = Image.new('RGB', (1100, 650), '#f4f1e6')
    draw = ImageDraw.Draw(image)
    for y, line in enumerate(['SYNTHETIC SCANNED REPORT', 'Patient: Synthetic patient 001', 'Encounter: enc-demo', 'This page has no selectable text.', 'Manual review is required.']):
        draw.text((55, 70 + y * 70), line, fill='#263c33', font_size=32)
    c.drawImage(ImageReader(image), 40, 330, width=515, height=304)

def selectable(c):
    c.setFont('Helvetica-Bold', 18)
    c.drawString(45, 775, 'SYNTHETIC LABORATORY REPORT')
    c.setFont('Helvetica', 12)
    for i, line in enumerate(['Patient: Synthetic patient 001', 'Encounter: enc-demo', 'Source: demo laboratory | 22 September 2026', 'Potassium 6.4 mmol/L', 'This is synthetic acceptance-test material, not clinical guidance.']):
        c.drawString(45, 730 - i * 29, line)

for name in ['selectable-report', 'scanned-report', 'partial-report']:
    c = canvas.Canvas(str(OUT / f'{name}.pdf'), pagesize=A4)
    c.setTitle(f'Noteguard synthetic {name}')
    if name == 'scanned-report': scan(c)
    else: selectable(c)
    if name == 'partial-report': c.showPage(); scan(c)
    c.save()

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='NGTitle', fontName='Helvetica-Bold', fontSize=25, leading=29, textColor=colors.HexColor('#123e38'), spaceAfter=16))
styles.add(ParagraphStyle(name='NGHead', fontName='Helvetica-Bold', fontSize=12, leading=16, textColor=colors.HexColor('#123e38'), spaceBefore=12, spaceAfter=7))
styles.add(ParagraphStyle(name='NGBody', fontName='Helvetica', fontSize=9.5, leading=14, textColor=colors.HexColor('#263c33'), spaceAfter=8))
story=[]
def p(text, style='NGBody'): story.append(Paragraph(text, styles[style]))
def table(rows, widths):
    t=Table([[Paragraph(str(v),styles['NGBody']) for v in row] for row in rows],colWidths=widths,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0e4')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dce2d7'))]))
    story.append(t)

p('NIGHTINGALE / NOTEGUARD', 'NGHead')
p('A second look at<br/>the supplied record.', 'NGTitle')
p('Technical brief | 22 September 2026 | Independent synthetic demonstrator')
p('1. Product and architecture', 'NGHead')
p('Noteguard reviews multidisciplinary documentation for one encounter. It raises evidence-linked questions, assigns accountable owners, records human dispositions, and shows unresolved closure risk. It neither diagnoses nor writes the authoritative medical record.')
table([['Local data flow','Responsibility'],['Pasted text / selectable PDF','Author, discipline, encounter, source time, source namespace and version'],['Immutable source version','SHA-256, exact text offsets, PDF pages and extraction status'],['Normalisation + version comparison','Bounded English assertions; newest eligible version; prior versions retained'],['Deterministic reconciliation','Six check categories; Tier 1/2/3; exact evidence; rule version'],['Human review','Accept, edit/reassign, dismiss, resolve, supersede or reopen; rationale and time'],['Questions + summary','Source cutoff, open priorities, evidence, owners and human decisions']],[180,319])
p('Deployment boundary', 'NGHead')
p('A static Vite-built PWA runs all clinical parsing and review in browser memory. PDF.js renders locally with PDF scripting/eval disabled. No API, model, analytics or clinical database is used. Refresh/reset clears case content and decisions; the service worker does not cache or intercept requests. Export is an explicit user action.')
p('This chooses the briefs\' browser-memory demonstrator exception. Demo role checks are bypassable and are not production authentication. Real patient data must not be entered. The previous Nightingale application is not modified.')
story.append(PageBreak())
p('2. Source and decision relationships', 'NGTitle')
table([['Entity','Contract'],['Encounter / team','Synthetic encounter, clinic, responsible clinician and declared team membership.'],['Source version','Namespace + source ID + version + encounter yield stable version ID. Source time and import time are distinct. SHA-256 covers original PDF bytes or text; text has a separate checksum.'],['Evidence','Version ID + exact character start/end + quote; PDF page when available. Unreadable attachments use page/extraction evidence, never invented text spans.'],['Flag','Stable identity from rule version, category and evidence. Tier, owner, contributors, current applicability, status, reason and creation time.'],['Decision','Actor, action, owner, rationale, time and usefulness feedback. Stored only for the page session.'],['Audit / provenance','Allowlisted content-free audit events are separate from evidence links. The in-memory audit is not a durable tamper-evident stream.'],['Summary / question','Derived from supplied versions and flags, with cutoff and source citations. Missing-documentation answers include inspected version IDs.']],[116,383])
p('Time and source integrity', 'NGHead')
p('Checks consider only sources whose event and import times are at or before the cutoff, selecting the greatest version per source. Identical re-imports are idempotent; changed content or metadata under the same version is rejected. Old evidence continues to resolve against the old source. No raw text is overwritten.')
p('Lifecycle safety', 'NGHead')
p('Open, accepted and edited Tier 1 concerns remain blockers. Dismissal, resolution and supersession require an authorised demo clinician and a rationale. Re-evaluation may mark evidence no longer current but never silently closes any existing concern. A current concern cannot be superseded. Reassignment does not prove handoff receipt or work completion.')
p('PDF uncertainty', 'NGHead')
p('Selectable-text coverage is a page-level heuristic, not proof the document was fully understood. Sparse, scanned, encrypted or failed extraction is surfaced for manual review. Partial PDFs preserve readable text and identify unread pages. Files are capped at 10 MB and extraction at 50 pages; originals stay in memory.')
story.append(PageBreak())
p('3. Checks, evidence and limits', 'NGTitle')
table([['Check','Expected behaviour'],['Critical observation / Tier 1','Potassium 6.4 mmol/L triggers when no later recognised clinician response appears. This brief-specified demo threshold is not a validated clinical rule.'],['Allergy / Tier 1','NKDA against explicit penicillin allergy cites both sources. A later explicit clinician reconciliation can suppress a new candidate.'],['Dose / Tier 2','Supported oral medicines, matching frequencies and different mg doses prompt review unless an explicit matching clinician dose change exists.'],['Pending result / Tier 2','A recognised owner and explicit future ISO deadline are both required for supported action types.'],['Extraction / Tier 2','Unreadable or partial PDF creates an owned review concern linked to attachment/page.'],['Version / Tier 3','Changed or exactly repeated source versions produce review questions, not diagnoses or automatic contradictions.']],[140,359])
p('Honest questions', 'NGHead')
p('Answers are restricted to documented, not documented in supplied sources, conflicting, incomplete extraction, or requires human review. Positive ECG evidence requires a recognised performed/completed assertion. An empty match means no recognised assertion in the supplied material, never that care did not occur.')
p('Language and clinical limits', 'NGHead')
p('English, line-oriented phrases only. The supported vocabulary is documented in INPUT_CONTRACT.md. This is not general clinical NLP, an exhaustive interaction checker or a multilingual system. Free wording, ambiguous negation, timing and dose changes can be missed. Reviewers must inspect original records. No clinical sensitivity/specificity or one-minute usability claim is established.')
p('Verification and AI', 'NGHead')
p('Automated domain tests cover true/false cases, exact grounding, version integrity, cutoff, decision preservation, policy simulation and redaction. Browser checks cover actual PDF intake, evidence navigation, mobile layout, refresh reset, storage/egress and summary export. See acceptance.md for measured results. External AI is deliberately absent; any future AI can only explain a bounded, verified evidence cluster after approved redaction.')
story.append(PageBreak())
p('4. Production path and governance', 'NGTitle')
p('Security that must precede a real deployment', 'NGHead')
p('Authenticate with an approved identity provider. Enforce clinic and care-team encounter membership on every server read and decision, including direct-object access; admin is not a clinical superuser. Add encrypted approved storage, TLS, short-lived document access and private/no-store clinical responses. Scan uploads and isolate PDF/OCR processing. Keep identifiers, text and prompts out of logs, URLs and analytics. The demo does not implement these production guarantees.')
p('Redaction is a boundary, not permission to disclose', 'NGHead')
p('The tested local stage replaces known names, national IDs, phones, email and common tagged IDs in a derived copy and preserves offset mappings. Unknown names and unusual formats remain a limitation. Original sources are unchanged. An external service still needs approval, retention terms and a governed egress policy; no such service is called here.')
p('Vendor-neutral integration', 'NGHead')
p('Read-only FHIR R4 + SMART App Launch is the baseline design. Patient/Encounter/CareTeam/PractitionerRole define context; DocumentReference/Binary/Composition carry documents; Observation, DiagnosticReport, MedicationRequest and AllergyIntolerance carry structured facts; Provenance and AuditEvent retain lineage. HL7 v2, CDA/XDS and file adapters map to the same source namespace/version/checksum contract. Idempotency is source identity + version. Any future write-back is a separate human-authorised reconciliation artifact or Task, never a source overwrite.')
p('Future audio schema only', 'NGHead')
p('Reserve audio_asset_id, transcript_id/version, speaker label, start/end milliseconds, transcription confidence and consent status in the production source extension. No audio recording, speech recognition or diarisation is implemented.')
p('Governed learning', 'NGHead')
p('Structured disposition/usefulness/ownership feedback can propose dictionary or rule changes. Version, evaluate offline against clinician-labelled cases, approve clinically, monitor release and retain rollback. Measure actionability, false positives, missed concerns and response time in a pilot. Current aggregates are synthetic session counts, not validation metrics. Quality/Risk/Legal reporting must expose aggregates only to authorised roles.')
p('Design evidence and deliverables', 'NGHead')
p('Starmer et al., NEJM 2014, doi:10.1056/NEJMsa1405556 supports structured handoff research; it does not validate this app. Wang et al., JAMA Internal Medicine 2017, doi:10.1001/jamainternmed.2017.1548 motivates source and copy history visibility. AHRQ TeamSTEPPS Handoff (2023) informs explicit responsibility and questions. Research notes, input cases, tests, README, attribution and a recorded demo accompany this brief.')

def footer(c,doc):
    c.setStrokeColor(colors.HexColor('#dce2d7'));c.line(48,42,547,42)
    c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#68756c'))
    c.drawString(48,29,'NOTEGUARD | Synthetic demonstrator | Human review required')
    c.drawRightString(547,29,str(doc.page))
doc=SimpleDocTemplate(str(OUT/'Noteguard_Technical_Brief.pdf'),pagesize=A4,rightMargin=48,leftMargin=48,topMargin=42,bottomMargin=56)
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print('Created three synthetic PDF inputs and technical brief.')
