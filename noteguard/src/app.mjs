import './style.css';
import {TEAM,ENCOUNTER,DISCIPLINES,RULE_VERSION,source,addSource,sha256,evaluate,reconcile,decide,blocking,terminal,resolve,summary,exportSummary,answerQuestion,metrics,canAccess,canDecide} from './core.mjs';
import {demoSources,responseSource} from './fixtures.mjs';
import {readPDF,renderPDF} from './pdf.mjs';
import {auditMetadata} from './privacy.mjs';

const app=document.querySelector('#app');
let sources=[],flags=[],files=new Map(),audit=[],user=TEAM[0],view='review',selected=null,question=null,error='',notice='',generation=0,busy=false;
let cutoff=new Date().toISOString();
const h=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const name=id=>TEAM.find(u=>u.id===id)?.name||id;
const date=value=>new Date(value).toLocaleString('en-SG',{dateStyle:'medium',timeStyle:'short'});
const recordAudit=action=>audit.push(auditMetadata(user.id,action,'allowed',new Date().toISOString()));
function run() {flags=reconcile(flags,evaluate(sources,cutoff));recordAudit('review');}
function clearCase(){generation++;sources=[];flags=[];files.clear();audit=[];selected=null;question=null;error='';notice='Case cleared. Nothing was saved.';busy=false;cutoff=new Date().toISOString();}
function evidenceButtons(evidence) {return evidence.map((e,i)=>{const s=sources.find(s=>s.versionId===e.versionId);return `<button class="evidence" data-source="${h(e.versionId)}" data-start="${e.start??''}" data-end="${e.end??''}" data-page="${e.page||1}"><span>↗ ${h(s?.sourceId)} · v${s?.version}${e.page?` · p${e.page}`:''}</span><small>${h(e.quote?.slice(0,115)||'Extraction limitation — inspect original')}</small></button>`;}).join('');}
function flagCard(f,i){return `<article class="flag tier${f.tier}" data-testid="flag-${f.category}">
  <div class="flag-top"><span class="badge t${f.tier}">TIER ${f.tier}</span><span class="status">${h(f.status)}</span><span class="muted">${h(f.category.replaceAll('-',' '))}</span></div>
  <h3>${h(f.title)}</h3><p>${h(f.reason)}</p>
  ${f.clarification?`<p class="decision"><strong>Human clarification:</strong> ${h(f.clarification)}</p>`:''}
  ${!f.current?'<p class="changed">New evidence changed this check. Human disposition is still required.</p>':''}
  <div class="evidence-list">${evidenceButtons(f.evidence)}</div>
  <div class="owner"><span class="avatar">${h(name(f.owner).split(' ').map(x=>x[0]).slice(-2).join(''))}</span><span>${h(name(f.owner))}<small>Accountable owner${f.contributors.length?' · Pharmacy involved':''}</small></span></div>
  <details><summary>Review & decision${f.history.length?` · ${f.history.length} recorded`:''}</summary>
  ${f.history.map(d=>`<div class="decision"><strong>${h(d.action)} · ${h(name(d.actor))}</strong><small>${date(d.time)} · owner ${h(name(d.owner))}</small><p>${h(d.rationale)}</p></div>`).join('')}
  ${canDecide(user,ENCOUNTER,f)?`<form data-decision="${i}"><label>Action<select name="action"><option value="accepted">Accept responsibility</option><option value="edited">Edit / reassign</option><option value="dismissed">Dismiss false positive</option><option value="resolved">Confirm work resolved</option>${!f.current?'<option value="superseded">Confirm superseded by new evidence</option>':''}<option value="open">Reopen for review</option></select></label>
  <label>Accountable owner<select name="owner">${TEAM.filter(u=>canAccess(u,ENCOUNTER)&&(f.tier!==1||u.role==='clinician')).map(u=>`<option value="${u.id}" ${u.id===f.owner?'selected':''}>${h(u.name)}</option>`).join('')}</select></label>
  <label>Rationale / evidence of action<textarea name="rationale" required maxlength="2000" placeholder="Why this decision? Cite the reviewed source or completed action."></textarea></label>
  <label>Human clarification (optional; original check stays visible)<textarea name="clarification" maxlength="2000" placeholder="Correct or clarify the proposed explanation.">${h(f.clarification||'')}</textarea></label>
  <label>Was the check useful?<select name="useful"><option value="unrated">Not rated</option><option value="useful">Useful</option><option value="not useful">Not useful</option><option value="wrong owner">Wrong owner</option><option value="stale wording">Stale wording</option><option value="missing rule">Missing rule</option></select></label>
  <button class="primary" type="submit">Record decision</button><p class="hint">Acceptance does not resolve underlying work.</p></form>`:'<p class="hint">This demo role cannot decide this concern.</p>'}
  </details><small class="rule">${h(f.checkVersion)} · raised ${date(f.createdAt)}</small></article>`;}
function reviewView(){const open=flags.filter(f=>!terminal(f.status));return `<div class="section-heading"><div><span class="eyebrow">RECONCILIATION</span><h2>What needs a second look</h2></div><span class="count">${open.length} unresolved</span></div>
  ${sources.length?`<div class="questions"><button class="bubble" data-question="ecg">Is an ECG documented?</button>${open.slice(0,3).map(f=>`<button class="bubble" data-question="${h(f.id)}">${h(f.title)}</button>`).join('')}</div>`:''}
  ${question?`<section class="answer"><button class="close" data-action="close-question" aria-label="Close question">×</button><strong>${h(question.status)}</strong><p>${h(question.uncertainty)}</p><small>Cutoff: ${date(question.cutoff)} · ${question.checkedVersions.length} source versions checked</small>${evidenceButtons(question.evidence)}${!question.evidence.length?'<p>No supporting assertion matched. Inspect the source inventory; this is not proof that the event did not occur.</p>':''}</section>`:''}
  ${!sources.length?'<section class="empty"><div class="empty-mark">↗</div><h3>Start with the record, not a conclusion.</h3><p>Load the synthetic encounter or add a record.<br>Every review question will lead back to its evidence.</p><button class="primary" data-action="demo">Load synthetic encounter</button></section>':open.length?open.map(f=>flagCard(f,flags.indexOf(f))).join(''):'<section class="empty"><h3>No unresolved checks in the supplied record set.</h3><p>This does not establish clinical safety or complete documentation.</p></section>'}
  ${flags.some(f=>terminal(f.status))?`<details class="completed"><summary>Decided concerns (${flags.filter(f=>terminal(f.status)).length})</summary>${flags.filter(f=>terminal(f.status)).map(f=>flagCard(f,flags.indexOf(f))).join('')}</details>`:''}`;}
function recordsView(){return `<div class="section-heading"><div><span class="eyebrow">SOURCE INVENTORY</span><h2>Who recorded what, and when</h2></div><button class="primary" data-action="import">Add record</button></div><p class="hint">All immutable versions are retained in this session. Rules use the latest eligible version of each source.</p>${[...sources].sort((a,b)=>a.time.localeCompare(b.time)).map(s=>`<article class="record"><div class="record-time">${date(s.time)}<small>${h(s.discipline)}</small></div><div><h3>${h(s.sourceId)} <span class="version">v${s.version}</span></h3><p>${h(name(s.owner))} · ${h(s.namespace)} · ${s.type.toUpperCase()}</p><span class="badge ${s.extraction==='complete'?'good':'warn'}">${s.extraction==='complete'?'Text available · manual verification required':s.extraction+' · manual review required'}</span><small>Imported ${date(s.importedAt)}</small><button class="text-button" data-source="${h(s.versionId)}" data-page="1">Read source ↗</button></div></article>`).join('')||'<p>No records loaded.</p>'}`;}
function importView(){return `<div class="section-heading"><div><span class="eyebrow">LOCAL INTAKE</span><h2>Add evidence to the encounter</h2></div></div><p class="hint">Synthetic data only. Text and PDFs stay in this tab. English demo phrases are supported; other wording requires manual review.</p><form id="intake" class="intake">
  <div class="form-grid"><label>Patient<input value="${h(ENCOUNTER.patient)}" disabled></label><label>Encounter<input value="${ENCOUNTER.id}" disabled></label>
  <label>Source ID<input name="sourceId" required maxlength="80" placeholder="e.g. nursing-review"></label><label>Source namespace<input name="namespace" value="manual-demo" required maxlength="80"></label>
  <label>Version<input name="version" type="number" value="1" min="1" max="10000" required></label><label>Source time (local)<input name="time" type="datetime-local" required value="${localDate(new Date())}"></label>
  <label>Author / owner<select name="owner">${TEAM.filter(u=>canAccess(u,ENCOUNTER)).map(u=>`<option value="${u.id}">${h(u.name)} · ${h(u.discipline)}</option>`).join('')}</select></label>
  <label>Input format<select name="type"><option value="text">Pasted text</option><option value="pdf">PDF attachment</option></select></label></div>
  <label>Clinical text<textarea name="text" rows="7" maxlength="200000" placeholder="One assertion per line. Example: Potassium 6.4 mmol/L"></textarea></label>
  <label>PDF (up to 10 MB / 50 pages)<input name="pdf" type="file" accept="application/pdf,.pdf"></label>
  <p class="hint">PDF page extraction is heuristic. Selectable text does not guarantee completeness; verify the original. Encrypted, oversized-page-count or unreadable PDFs are retained for manual review.</p>
  <button class="primary" type="submit" ${busy?'disabled':''}>${busy?'Reading locally…':'Import & run checks'}</button></form>`;}
function summaryView(){const data=summary(sources,flags,cutoff);return `<div class="section-heading"><div><span class="eyebrow">HANDOVER SNAPSHOT</span><h2>One record. Clear next questions.</h2></div><button class="primary" data-action="export">Export summary</button></div><section class="summary-sheet"><div class="summary-title"><strong>NOTEGUARD / REVIEW SUMMARY</strong><span>${date(data.generatedAt)}</span></div><h3>${h(ENCOUNTER.patient)}</h3><p>${ENCOUNTER.id} · Source cutoff ${date(cutoff)}</p><p class="review-statement">${h(data.statement)}</p><h3>Source timeline</h3>${data.sources.map(s=>`<p class="timeline-line"><time>${date(s.time)}</time> ${h(s.discipline)} · ${h(s.sourceId)} v${s.version} <button class="text-button" data-source="${s.versionId}" data-page="1">Source ↗</button></p>`).join('')||'<p>No sources.</p>'}<h3>Unresolved priorities</h3>${data.claims.map(c=>`<div class="summary-claim"><strong>Tier ${c.tier} · ${h(c.text)}</strong><p>${h(name(c.owner))} · ${c.status}${!c.current?' · changed evidence, human review pending':''}</p>${evidenceButtons(c.evidence)}</div>`).join('')||'<p>No unresolved priorities from the supported checks. This does not establish safety.</p>'}<h3>Recent human decisions</h3>${data.decisions.slice(-8).map(d=>`<p><strong>${h(d.action)}</strong> · ${h(name(d.actor))} · ${date(d.time)}<br>${h(d.rationale)}</p>`).join('')||'<p>No human decisions recorded.</p>'}</section>`;}
function governanceView(){const m=metrics(flags);return `<div class="section-heading"><div><span class="eyebrow">SESSION GOVERNANCE</span><h2>Learn from review. Keep the rules accountable.</h2></div></div><p class="hint">Aggregate-only demo view. Counts are from this tab, not clinical performance estimates. No automatic rule updates.</p><div class="metric-grid">${Object.entries(m).map(([k,v])=>`<div class="metric"><strong>${v}</strong><span>${h(k)}</span></div>`).join('')}</div><section class="panel"><h3>Governed improvement pathway</h3><p>Structured feedback → proposed change → versioned offline evaluation → clinical approval → monitored release → rollback.</p><p>False positives, missed concerns and response-time performance require clinician-labelled pilot data; they are not inferred from these counts.</p><p>Current rules: ${RULE_VERSION}. No rule was changed by the feedback above.</p></section><section class="panel"><h3>Access-control boundary</h3><p>This is a browser-memory demonstrator. Role and scope checks model workflow only. They are bypassable in developer tools and are not server authentication or production authorisation.</p><p>Production requires identity-backed encounter membership, server-side decision enforcement, approved storage and tamper-evident audit. None is claimed here.</p></section>`;}
function localDate(d){return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);}
function reader(){if(!selected)return '';const s=sources.find(s=>s.versionId===selected.id);if(!s)return '';const start=selected.start,end=selected.end;
  return `<div class="scrim" data-action="close-source"></div><aside class="reader" role="dialog" aria-modal="true" aria-label="Source evidence"><button class="close" data-action="close-source" aria-label="Close source">×</button><span class="eyebrow">IMMUTABLE SOURCE</span><h2>${h(s.sourceId)} <span class="version">v${s.version}</span></h2><p>${h(name(s.owner))} · ${h(s.discipline)}</p><p>${date(s.time)} · ${h(s.extraction)}</p><small class="hash">${h(s.versionId)}<br>SHA-256 ${h(s.checksum)}</small><h3>Exact extracted text</h3><pre>${start!==null&&end!==null?h(s.text.slice(0,start))+'<mark>'+h(s.text.slice(start,end))+'</mark>'+h(s.text.slice(end)):h(s.text||'No readable text. Inspect the original attachment.')}</pre>${s.type==='pdf'?`<h3>Original PDF · page ${selected.page}</h3><div class="pdf-controls"><button data-action="prev-page" ${selected.page<=1?'disabled':''}>Previous page</button><button data-action="next-page" ${selected.page>=s.pages.length?'disabled':''}>Next page</button></div><p class="hint" id="pdf-message">Rendering locally. Active PDF content is not executed.</p><canvas id="pdf-canvas"></canvas>`:''}<button class="secondary" data-action="close-source">Back to review</button></aside>`;}
function render(){
  const allowed=canAccess(user,ENCOUNTER),quality=user.role==='quality',block=blocking(flags).length;
  app.innerHTML=`<header class="topbar"><a class="brand" href="/" aria-label="Noteguard home"><span class="brand-mark">N<span>·</span></span><span>noteguard<small>BY NIGHTINGALE</small></span></a><span class="top-note">A second look. A clearer handover.</span><button class="secondary" data-action="reset">Reset session</button></header>
  <div class="demo-banner"><strong>SYNTHETIC DEMO</strong><span>Memory only · refresh clears all records and decisions · no server authentication · no external AI</span></div>
  <div class="layout"><aside class="sidebar"><span class="eyebrow">DEMO PERSPECTIVE</span><label class="sr-only" for="user">Demo role</label><select id="user">${TEAM.map(u=>`<option value="${u.id}" ${u.id===user.id?'selected':''}>${h(u.name)}</option>`).join('')}</select><p class="hint">Workflow simulation, not a secure login.</p><div class="encounter-card"><span class="eyebrow">ENCOUNTER</span><h3>${allowed?h(ENCOUNTER.patient):'Restricted workspace'}</h3><p>${allowed?'22 Sep 2026 · Demo clinic A':'Role/scope demonstration'}</p><span class="live-dot">${allowed?'Local session':'No clinical access'}</span></div>
  <nav>${(allowed?[['review','Review queue','01'],['records','Source records','02'],['summary','Handover summary','03'],['governance','Quality & safety','04']]:quality?[['governance','Quality & safety','04']]:[]).map(([id,label,n])=>`<button data-view="${id}" class="nav-item ${view===id?'active':''}"><span>${n}</span>${label}</button>`).join('')}</nav><div class="sidebar-bottom"><strong>Evidence before inference.</strong><p>Questions for the care team.<br>Decisions by the care team.</p><small>English bounded checks · ${RULE_VERSION}</small></div></aside>
  <main>${error?`<div class="error" role="alert">${h(error)}</div>`:''}${notice?`<div class="notice" role="status">${h(notice)}</div>`:''}
  ${allowed?`<section class="workspace-top"><div><span class="eyebrow">ENCOUNTER REVIEW</span><h1>The record, reconciled.</h1><p>See the evidence. Assign the next step. Keep uncertainty visible.</p></div><div class="top-actions"><button class="secondary" data-action="demo">Load demo</button><button class="primary" data-action="import">＋ Add record</button></div></section>
  <section class="status-strip"><div><strong>${sources.length}</strong><span>source versions</span></div><div><strong>${flags.filter(f=>!terminal(f.status)).length}</strong><span>review questions</span></div><div class="closure ${block?'blocked':'clear'}"><strong>${block?`${block} closure blocker${block>1?'s':''}`:'No Tier 1 blockers'}</strong><span>${block?'Human disposition required':'Not a clinical clearance'}</span></div></section>
  <div class="cutoff"><span>Sources through <strong>${date(cutoff)}</strong></span><details><summary>Change cutoff</summary><form id="cutoff-form"><label>Review cutoff<input type="datetime-local" name="cutoff" required value="${localDate(new Date(cutoff))}"></label><button type="submit">Run checks</button></form></details>${sources.length?'<button class="text-button" data-action="response">＋ Add later clinician response (demo)</button>':''}</div>
  ${view==='import'?importView():view==='records'?recordsView():view==='summary'?summaryView():view==='governance'?governanceView():reviewView()}`:quality?governanceView():'<section class="empty"><h2>Encounter unavailable for this demo role</h2><p>No membership in this encounter’s care team.</p></section>'}</main></div>${allowed?reader():''}`;
  if(selected){document.querySelector('.reader .close')?.focus();document.querySelector('mark')?.scrollIntoView({block:'center'});const bytes=files.get(selected.id);if(bytes){const canvas=document.querySelector('#pdf-canvas');renderPDF(bytes,selected.page,canvas).then(()=>{if(canvas.isConnected)document.querySelector('#pdf-message').textContent='Original page rendered locally. Compare with extracted text above.';}).catch(()=>{if(canvas.isConnected)document.querySelector('#pdf-message').textContent='This attachment could not be rendered. Manual review in an approved PDF tool is required.';});}}
}
app.addEventListener('click',async event=>{
  const b=event.target.closest('button');if(!b||(!b.dataset.action&&!b.dataset.view&&!b.dataset.source&&!b.dataset.question))return;
  try{
    error='';notice='';
    if(b.dataset.view){view=b.dataset.view;question=null;render();return;}
    if(b.dataset.source){selected={id:b.dataset.source,start:b.dataset.start?Number(b.dataset.start):b.dataset.start==='0'?0:null,end:b.dataset.end?Number(b.dataset.end):null,page:Number(b.dataset.page)||1};render();return;}
    if(b.dataset.question){question=answerQuestion(b.dataset.question,sources,flags,cutoff);render();return;}
    const action=b.dataset.action;
    if(action==='reset'){clearCase();view='review';}
    if(action==='demo'){const epoch=++generation;busy=true;const loaded=await demoSources();if(epoch!==generation)return;sources=loaded;flags=[];files.clear();audit=[];cutoff='2026-09-22T06:00:00.000Z';run();view='review';selected=null;busy=false;notice='Six synthetic multidisciplinary records loaded. Synthetic review cutoff: 22 Sep 2026, 14:00 SGT. All checks run locally.';}
    if(action==='response'){const epoch=generation;const s=await responseSource();if(epoch!==generation)return;sources=addSource(sources,s);run();notice='Later response added. Old concerns remain until a human records their disposition.';}
    if(action==='import')view='import';
    if(action==='close-source')selected=null;
    if(action==='close-question')question=null;
    if(action==='prev-page')selected.page--;
    if(action==='next-page')selected.page++;
    if(action==='export'){
      const blob=new Blob([exportSummary(summary(sources,flags,cutoff),sources)],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='noteguard-review-summary.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice='Summary exported by your action. It contains synthetic source references and decisions.';
    }
    render();
  }catch(e){error=e.message;busy=false;render();}
});
app.addEventListener('change',event=>{if(event.target.id==='user'){clearCase();user=TEAM.find(u=>u.id===event.target.value);view=user.role==='quality'?'governance':'review';notice='Perspective changed. Prior case and pending input cleared.';render();}});
app.addEventListener('submit',async event=>{
  event.preventDefault();const form=event.target,data=new FormData(form);error='';notice='';
  try{
    if(form.id==='intake'){
      if(!canAccess(user,ENCOUNTER))throw Error('Encounter unavailable.');
      const epoch=generation,owner=TEAM.find(u=>u.id===data.get('owner')),type=data.get('type');let extracted={text:String(data.get('text')),extraction:'complete',pages:[]},bytes,fileChecksum;
      if(type==='pdf'){
        const file=data.get('pdf');if(!file?.size)throw Error('Select a PDF attachment.');if(file.size>10*1024*1024)throw Error('PDF exceeds the 10 MB demo limit.');
        bytes=await file.arrayBuffer();if(new TextDecoder().decode(bytes.slice(0,5))!=='%PDF-')throw Error('File is not a PDF.');
        busy=true;form.querySelector('button[type=submit]').disabled=true;form.querySelector('button[type=submit]').textContent='Reading locally…';
        fileChecksum=await sha256(bytes);extracted=await readPDF(bytes);
      }
      const s=await source({sourceId:String(data.get('sourceId')),namespace:String(data.get('namespace')),version:Number(data.get('version')),time:new Date(String(data.get('time'))).toISOString(),owner:owner.id,discipline:owner.discipline,encounter:ENCOUNTER.id,type,fileChecksum,...extracted});
      if(epoch!==generation)return;
      sources=addSource(sources,s);if(bytes)files.set(s.versionId,bytes);cutoff=new Date(Math.max(Date.parse(cutoff),Date.now())).toISOString();recordAudit('import');run();busy=false;view='records';notice='Source retained in memory. Review extraction against the original.';
    }else if(form.dataset.decision){const f=flags[Number(form.dataset.decision)];flags=decide(flags,f.id,user,data.get('action'),data.get('rationale'),data.get('owner'),undefined,data.get('useful'),data.get('clarification')||'');recordAudit(data.get('action'));notice='Human decision recorded in this session.';
    }else if(form.id==='cutoff-form'){cutoff=new Date(String(data.get('cutoff'))).toISOString();run();question=null;}
    render();
  }catch(e){error=e.message;busy=false;render();}
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&selected){selected=null;render();}
  if(event.key==='Tab'&&selected){const focus=[...document.querySelectorAll('.reader button:not([disabled])')];if(event.shiftKey&&document.activeElement===focus[0]){event.preventDefault();focus.at(-1)?.focus();}else if(!event.shiftKey&&document.activeElement===focus.at(-1)){event.preventDefault();focus[0]?.focus();}}
});
window.addEventListener('pagehide',()=>clearCase());
window.addEventListener('pageshow',e=>{if(e.persisted){clearCase();render();}});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
render();
