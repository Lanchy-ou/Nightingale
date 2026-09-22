export const RULE_VERSION = 'noteguard-en-1.0';
export const DISCIPLINES = ['clinician', 'nursing', 'pharmacy', 'physiotherapy', 'counselling/social work', 'other'];
export const TEAM = [
  { id: 'lee', name: 'Dr Alex Lee', role: 'clinician', discipline: 'clinician', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'tan', name: 'Nurse Jamie Tan', role: 'staff', discipline: 'nursing', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'patel', name: 'Sam Patel', role: 'staff', discipline: 'pharmacy', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'chen', name: 'Robin Chen', role: 'staff', discipline: 'physiotherapy', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'lim', name: 'Casey Lim', role: 'staff', discipline: 'counselling/social work', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'wong', name: 'Taylor Wong', role: 'staff', discipline: 'other', clinic: 'demo-a', encounters: ['enc-demo'] },
  { id: 'quality', name: 'Quality reviewer', role: 'quality', discipline: 'other', clinic: 'demo-a', encounters: [] },
  { id: 'outsider', name: 'Other clinic reviewer', role: 'clinician', discipline: 'clinician', clinic: 'demo-b', encounters: ['enc-other'] },
];
export const ENCOUNTER = Object.freeze({ id: 'enc-demo', patient: 'Synthetic patient 001', clinic: 'demo-a', clinician: 'lee' });
export const terminal = status => ['dismissed', 'resolved', 'superseded'].includes(status);
export function canAccess(user, encounter) {
  return !!user && ['clinician', 'staff'].includes(user.role) && user.clinic === encounter.clinic && user.encounters.includes(encounter.id);
}
export function canDecide(user, encounter, flag) {
  return canAccess(user, encounter) && (user.role === 'clinician' || (flag.tier !== 1 && flag.owner === user.id));
}
export async function sha256(value) {
  const bytes = typeof value === 'string' ? new TextEncoder().encode(value) : value;
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
}
function freeze(value) {
  Object.values(value).forEach(v => { if (v && typeof v === 'object') freeze(v); });
  return Object.freeze(value);
}
export async function source(input, importedAt = new Date().toISOString()) {
  if (!input.sourceId?.trim() || !input.namespace?.trim() || !Number.isInteger(input.version) || input.version < 1 ||
      !DISCIPLINES.includes(input.discipline) || !TEAM.some(u => u.id === input.owner && u.discipline === input.discipline && canAccess(u, ENCOUNTER)) ||
      !Number.isFinite(Date.parse(input.time)) || !Number.isFinite(Date.parse(importedAt)) || input.encounter !== ENCOUNTER.id ||
      !['text', 'pdf'].includes(input.type) || (input.type === 'text' && !input.text?.trim())) throw Error('Invalid source metadata or empty text.');
  const text = input.text || '';
  if (text.length > 200000) throw Error('Source exceeds the 200,000-character demo limit.');
  const key = JSON.stringify([input.encounter, input.namespace.trim(), input.sourceId.trim(), input.version]);
  const versionId = 'src-' + (await sha256(key)).slice(0, 24);
  const checksum = input.fileChecksum || await sha256(text);
  return freeze({ versionId, namespace: input.namespace.trim(), sourceId: input.sourceId.trim(), version: input.version,
    encounter: input.encounter, patient: ENCOUNTER.patient, owner: input.owner, discipline: input.discipline,
    time: new Date(input.time).toISOString(), importedAt, type: input.type, text, checksum,
    textChecksum: await sha256(text), extraction: input.extraction || 'complete', pages: input.pages || [],
    audio: null });
}
export function addSource(sources, next) {
  const existing = sources.find(s => s.versionId === next.versionId);
  if (existing) {
    const stable = s => JSON.stringify({ ...s, importedAt: '' });
    if (stable(existing) !== stable(next)) throw Error('This source version already exists with different content or metadata. Import a new version.');
    return sources;
  }
  return [...sources, next];
}
export function currentSources(sources, cutoff) {
  cutoff=new Date(cutoff).toISOString();
  const selected = new Map();
  for (const s of sources.filter(s => s.encounter === ENCOUNTER.id && s.time <= cutoff && s.importedAt <= cutoff)) {
    const key = JSON.stringify([s.encounter, s.namespace, s.sourceId]);
    if (!selected.has(key) || selected.get(key).version < s.version) selected.set(key, s);
  }
  return [...selected.values()].sort((a,b) => a.time.localeCompare(b.time) || a.versionId.localeCompare(b.versionId));
}
export function span(s, start, end) {
  if (start < 0 || end <= start || end > s.text.length) throw Error('Invalid evidence span.');
  return { versionId: s.versionId, start, end, quote: s.text.slice(start, end), page: s.pages.find(p => start >= p.start && start < p.end)?.number || null };
}
export function resolve(sources, e) {
  const s = sources.find(x => x.versionId === e.versionId);
  if (!s) throw Error('Source version is unavailable.');
  if (e.kind === 'extraction') return { source: s, text: `Extraction: ${s.extraction}`, page: e.page };
  if (!Number.isInteger(e.start) || !Number.isInteger(e.end) || e.start < 0 || e.end <= e.start || e.end > s.text.length || s.text.slice(e.start, e.end) !== e.quote) throw Error('Evidence does not match the immutable source.');
  return { source: s, text: e.quote, page: e.page };
}
function lines(s) {
  return [...s.text.matchAll(/[^\r\n]+/g)].map(m => ({ text: m[0], evidence: span(s, m.index, m.index + m[0].length), source: s }));
}
const noAssertion = t => /\b(no|not|denies|denied|without|possible|suspected|if|consider|planned|pending)\b/i.test(t);
const matching = (all, regex) => all.filter(l => regex.test(l.text) && !noAssertion(l.text));
export function evaluate(sources, cutoff) {
  if (!Number.isFinite(Date.parse(cutoff))) throw Error('Invalid source cutoff.');
  const active = currentSources(sources, cutoff), all = active.flatMap(lines), flags = [];
  const emit = (category, tier, title, reason, evidence, owner = ENCOUNTER.clinician, contributors = []) => {
    evidence.forEach(e => resolve(sources, e));
    flags.push({ id: JSON.stringify([RULE_VERSION, category, ...evidence.map(e => [e.versionId, e.start ?? e.page, e.end])]), category, tier, title, reason, evidence,
      owner, contributors, checkVersion: RULE_VERSION, createdAt: cutoff, status: 'open', current: true, history: [] });
  };
  for (const l of all) {
    // This bounded fixture threshold is an acceptance example, not a validated clinical rule.
    const k = l.text.match(/^\s*(?:potassium|K\+)\s*:?\s*(\d+(?:\.\d+)?)\s*mmol\/L\b/i);
    if (k && +k[1] >= 6.4 && !noAssertion(l.text)) {
      const responses = matching(all, /^\s*(?:potassium|K\+)\s+(?:reviewed|treated|repeated)\b/i)
        .filter(r => r.source.discipline === 'clinician' && r.source.time > l.source.time);
      if (!responses.length) emit('critical-observation', 1, 'Is a response to the potassium documented?',
        'A potassium value meets the demo check; a later clinician response is not documented in supplied sources.', [l.evidence]);
    }
  }
  const nkda = all.filter(l => /^\s*(?:NKDA|No known drug allergies)\s*[.!]?\s*$/i.test(l.text));
  const allergy = matching(all, /^\s*(?:Allergy\s*:\s*penicillin|Penicillin allergy)\b/i);
  for (const a of nkda) for (const b of allergy) if (a.source.versionId !== b.source.versionId) {
    const clarification = matching(all, /^\s*Allergy reconciled\s*:\s*(?:penicillin allergy confirmed|NKDA confirmed)\s*[.!]?\s*$/i)
      .some(r => r.source.discipline === 'clinician' && r.source.time > a.source.time && r.source.time > b.source.time);
    if (!clarification) emit('allergy-conflict', 1, 'Which allergy entry is current?', 'NKDA and a named penicillin allergy appear in different records.', [a.evidence,b.evidence]);
  }
  const meds = all.map(l => ({ ...l, match: l.text.match(/^\s*(amlodipine|lisinopril|metformin)\s+(\d+(?:\.\d+)?)\s*(mg)\s+(oral)\s+(daily|twice daily)\s*[.!]?\s*$/i) })).filter(l => l.match);
  for (let i=0;i<meds.length;i++) for(let j=i+1;j<meds.length;j++) {
    const a=meds[i], b=meds[j];
    if (a.source.versionId === b.source.versionId || a.match[1].toLowerCase() !== b.match[1].toLowerCase() || a.match[2] === b.match[2] || a.match[5].toLowerCase() !== b.match[5].toLowerCase()) continue;
    const adjustment = new RegExp(`^\\s*${a.match[1]} dose changed from ${a.match[2]} mg to ${b.match[2]} mg oral ${b.match[5]}\\s*[.!]?\\s*$`, 'i');
    const changed = all.some(r => r.source.discipline === 'clinician' && r.source.time >= b.source.time && r.source.time > a.source.time && adjustment.test(r.text));
    if (!changed) emit('dose-conflict', 2, `Please reconcile ${a.match[1].toLowerCase()} doses`, 'Comparable oral schedules contain different doses without a documented matching dose change.', [a.evidence,b.evidence], ENCOUNTER.clinician, ['patel']);
  }
  for (const l of all) {
    const pending = l.text.match(/^\s*(?:Pending|Awaiting)\s+(blood culture|culture|blood test|ECG)(?: result)?\b/i);
    if (!pending || /\b(?:not pending|cancelled|canceled)\b/i.test(l.text)) continue;
    const key = pending[1].toLowerCase();
    const related = all.filter(r => r.source.time >= l.source.time && new RegExp(`^\\s*(?:Pending|Awaiting|Follow-up for)\\s+${key}(?: result)?\\b`, 'i').test(r.text));
    const arranged = related.some(r => {
      const owner = r.text.match(/\bowner\s*:\s*([a-z]+)\b/i)?.[1]?.toLowerCase();
      const due = r.text.match(/\bdue\s*:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2}))/i)?.[1];
      return TEAM.some(u => u.id === owner && canAccess(u, ENCOUNTER)) && due && Number.isFinite(Date.parse(due)) && Date.parse(due) > Date.parse(r.source.time);
    });
    if (!arranged) emit('pending-followup', 2, `Who owns the pending ${key}?`, 'A recognised owner and an explicit future deadline are not both documented for this action.', [l.evidence], l.source.owner);
  }
  for (const s of active) {
    if (s.extraction !== 'complete') emit('extraction-review', 2, 'This document needs a manual read', 'Text extraction is incomplete. No conclusion can be drawn about the unread portions.',
      (s.pages.filter(p => p.status !== 'complete').length ? s.pages.filter(p => p.status !== 'complete') : [{number:1}]).map(p => ({versionId:s.versionId,kind:'extraction',page:p.number})), s.owner);
    const prior = sources.filter(p => p.namespace === s.namespace && p.sourceId === s.sourceId && p.encounter === s.encounter && p.version < s.version && p.importedAt <= cutoff && p.time <= cutoff).sort((a,b)=>b.version-a.version)[0];
    if (prior && prior.text && s.text) {
      const same = prior.text === s.text;
      emit(same ? 'copied-forward' : 'version-change', 3, same ? 'Is this carried-forward record still current?' : 'What changed in this source version?',
        same ? 'The new version repeats the prior text. This is a review question, not proof of stale care.' : 'Source text changed. Review both versions; change alone is not a clinical contradiction.',
        [span(prior,0,prior.text.length),span(s,0,s.text.length)], s.owner);
    }
  }
  return flags.sort((a,b)=>a.tier-b.tier || a.id.localeCompare(b.id));
}
export function reconcile(previous, candidates) {
  const next = candidates.map(c => {
    const old = previous.find(p => p.id === c.id);
    return old ? {...old, current:true, reason:c.reason} : c;
  });
  for (const old of previous) if (!next.some(c => c.id === old.id)) next.push({...old,current:false});
  // A rerun changes applicability only. Human decisions never disappear or auto-close.
  return next.sort((a,b)=>a.tier-b.tier || a.id.localeCompare(b.id));
}
export function decide(flags, id, user, action, rationale, owner, time = new Date().toISOString(), useful = 'unrated', clarification = '') {
  const f = flags.find(f=>f.id===id);
  if (!f || !canDecide(user, ENCOUNTER, f)) throw Error('This demo role cannot decide this concern.');
  if (!['accepted','edited','dismissed','resolved','superseded','open'].includes(action)) throw Error('Unknown decision.');
  if (!rationale?.trim()) throw Error('Record a rationale for this decision.');
  const assignee = TEAM.find(u=>u.id===owner);
  if (!canAccess(assignee, ENCOUNTER) || (f.tier===1 && assignee.role!=='clinician')) throw Error('A Tier 1 concern must remain assigned to a clinician.');
  if (action==='superseded' && f.current) throw Error('A currently triggered concern cannot be superseded.');
  const decision = { actor:user.id, action, rationale:rationale.trim(), owner, time, useful, clarification:clarification.trim() };
  return flags.map(x=>x.id===id ? {...x,status:action,owner,clarification:clarification.trim()||x.clarification,history:[...x.history,decision]} : x);
}
export const blocking = flags => flags.filter(f=>f.tier===1 && !terminal(f.status));
export function answerQuestion(kind, sources, flags, cutoff) {
  const active = currentSources(sources,cutoff);
  if (kind === 'ecg') {
    const evidence = active.flatMap(lines).filter(l=>/^\s*ECG (?:performed|completed)\b/i.test(l.text) && !noAssertion(l.text)).map(l=>l.evidence);
    return { status:evidence.length?'documented':active.some(s=>s.extraction!=='complete')?'incomplete extraction':'not documented in supplied sources', evidence, cutoff,
      checkedVersions:active.map(s=>s.versionId), uncertainty:'Limited to supplied versions and recognised English phrases; absence is not proof an event did not occur.' };
  }
  const f=flags.find(f=>f.id===kind);
  if (!f) throw Error('Unknown question.');
  return { status:!f.current || terminal(f.status)?'requires human review':f.category==='extraction-review'?'incomplete extraction':f.category.includes('conflict')?'conflicting':'requires human review', evidence:f.evidence,cutoff,
    checkedVersions:active.map(s=>s.versionId),uncertainty:'A review question, not a diagnosis. Human disposition does not establish a clinical fact.' };
}
export function summary(sources, flags, cutoff, now = new Date().toISOString()) {
  const current = currentSources(sources,cutoff);
  const claims = flags.filter(f=>f.tier<=2 && !terminal(f.status)).map(f=>({text:f.title,evidence:f.evidence,status:f.status,owner:f.owner,current:f.current,tier:f.tier,clarification:f.clarification||''}));
  claims.forEach(c=>c.evidence.forEach(e=>resolve(sources,e)));
  return { generatedAt:now,cutoff,encounter:ENCOUNTER,claims, sources:current,
    decisions:flags.flatMap(f=>f.history.map(d=>({...d,title:f.title,evidence:f.evidence}))),
    statement:'Human review required. This is a supplied-record reconciliation summary, not the authoritative medical record or permission to discharge.' };
}
export function exportSummary(data, sources) {
  const citation = e => {
    const {source:s}=resolve(sources,e);
    const location=e.kind==='extraction'?`page ${e.page}, ${s.extraction}`:`chars ${e.start}-${e.end}${e.page?`, page ${e.page}`:''}`;
    return `${s.namespace}/${s.sourceId} v${s.version} (${s.versionId}; SHA-256 ${s.checksum}) ${location}`;
  };
  return [`NOTEGUARD | ${data.encounter.patient} | ${data.encounter.id}`,`Generated: ${data.generatedAt}`,`Source cutoff: ${data.cutoff}`,data.statement,'','SOURCE TIMELINE',
    ...data.sources.map(s=>`${s.time} | ${s.discipline} | ${s.owner} | ${s.namespace}/${s.sourceId} v${s.version} | ${s.extraction} | ${s.versionId} | SHA-256 ${s.checksum}`),
    '', 'UNRESOLVED PRIORITIES',...data.claims.map(c=>`Tier ${c.tier}: ${c.text} [${c.status}; owner ${c.owner}; ${c.current?'currently triggered':'changed evidence - human review pending'}]${c.clarification?`\nHuman clarification: ${c.clarification}`:''}\n${c.evidence.map(citation).join('\n')}`),
    '', 'HUMAN DECISIONS',...data.decisions.map(d=>`${d.time} | ${d.actor} | ${d.action} | owner ${d.owner} | ${d.rationale}\n${d.evidence.map(citation).join('\n')}`)].join('\n');
}
export function metrics(flags) {
  const decisions=flags.flatMap(f=>f.history);
  return { open:flags.filter(f=>!terminal(f.status)).length, tier1:blocking(flags).length, accepted:decisions.filter(d=>d.action==='accepted').length,
    dismissed:decisions.filter(d=>d.action==='dismissed').length, useful:decisions.filter(d=>d.useful==='useful').length,
    notUseful:decisions.filter(d=>d.useful==='not useful').length, decisions:decisions.length };
}
