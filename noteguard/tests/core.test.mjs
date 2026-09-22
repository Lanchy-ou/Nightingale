import {test} from 'node:test';
import assert from 'node:assert/strict';
import {source,addSource,evaluate,reconcile,resolve,decide,blocking,canAccess,canDecide,answerQuestion,summary,exportSummary,TEAM,ENCOUNTER,currentSources,span} from '../src/core.mjs';
import {redact,auditMetadata} from '../src/privacy.mjs';
import {demoSources,responseSource} from '../src/fixtures.mjs';
const cutoff='2026-09-23T00:00:00.000Z';
const make=(text,extra={})=>source({sourceId:'note',namespace:'test',version:1,owner:'lee',discipline:'clinician',encounter:'enc-demo',time:'2026-09-22T01:00:00Z',type:'text',text,...extra},'2026-09-22T06:00:00Z');
test('test_critical_observation_routing: later clinician response suppresses the candidate, not an existing human concern',async()=>{
 const ss=await demoSources(),before=evaluate(ss,cutoff),f=before.find(f=>f.category==='critical-observation');assert.equal(f.tier,1);assert.equal(f.owner,'lee');
 const after=evaluate([...ss,await responseSource()],cutoff);assert.ok(!after.some(f=>f.category==='critical-observation'));
 const merged=reconcile(before,after);assert.equal(merged.find(x=>x.id===f.id).current,false);assert.ok(blocking(merged).length>0);
});
test('negated, planned, unrelated, earlier and nursing responses do not suppress critical observation',async()=>{
 const k=await make('Potassium 6.4 mmol/L',{sourceId:'k',owner:'tan',discipline:'nursing'});
 for(const text of ['Potassium not reviewed','Potassium reviewed if repeat is high','Potassium reviewed; treatment planned','ECG reviewed','Potassium review planned']){
  const r=await make(text,{sourceId:'r',time:'2026-09-22T02:00:00Z'});assert.ok(evaluate([k,r],cutoff).some(f=>f.category==='critical-observation'),text);
 }
 for(const extra of [{time:'2026-09-22T00:00:00Z'},{time:'2026-09-22T02:00:00Z',owner:'tan',discipline:'nursing'}])assert.ok(evaluate([k,await make('Potassium reviewed', {sourceId:'r',...extra})],cutoff).some(f=>f.category==='critical-observation'));
});
test('test_cross_note_conflicts: both-source allergy evidence and medication ownership',async()=>{
 const ss=await demoSources(),f=evaluate(ss,cutoff);const a=f.find(x=>x.category==='allergy-conflict'),m=f.find(x=>x.category==='dose-conflict');
 assert.equal(a.tier,1);assert.equal(a.evidence.length,2);a.evidence.forEach(e=>assert.ok(resolve(ss,e).text));assert.equal(m.tier,2);assert.ok(m.contributors.includes('patel'));
 assert.ok(!evaluate([...ss,await responseSource()],cutoff).some(f=>f.category.includes('conflict')));
});
test('negated penicillin allergy and unrelated or wrong dose change do not invent/suppress conflict',async()=>{
 const a=await make('NKDA',{sourceId:'a'}),b=await make('Penicillin allergy denied',{sourceId:'b'});assert.equal(evaluate([a,b],cutoff).length,0);
 const ss=await demoSources(),change=await make('Amlodipine dose changed from 2 mg to 10 mg oral daily',{sourceId:'change',time:'2026-09-22T06:00:00Z'});assert.ok(evaluate([...ss,change],cutoff).some(f=>f.category==='dose-conflict'));
});
test('test_pending_owner_and_time: either missing, invalid owner, invalid date or expired deadline flags',async()=>{
 for(const text of ['Pending blood culture result','Pending blood culture result; owner: lee','Pending blood culture result; due: 2026-09-23T14:00:00Z','Pending blood culture result; owner: outsider; due: 2026-09-23T14:00:00Z','Pending blood culture result; owner: lee; due: 2026-09-20T14:00:00Z']) assert.ok(evaluate([await make(text)],cutoff).some(f=>f.category==='pending-followup'),text);
 assert.equal(evaluate([await make('Pending blood culture result; owner: lee; due: 2026-09-23T14:00:00Z')],cutoff).length,0);
});
test('test_pdf_extraction_boundary: empty and partial documents retain version-linked page evidence',async()=>{
 for(const extraction of ['unreadable','partial']){
 const s=await make('',{type:'pdf',extraction,pages:[{number:1,start:0,end:0,status:'needs_review'}]});const f=evaluate([s],cutoff)[0];assert.equal(f.category,'extraction-review');assert.equal(f.tier,2);assert.equal(resolve([s],f.evidence[0]).source,s);
 }
});
test('test_access_control: demo policy only, NOT a server security test',async()=>{
 assert.equal(canAccess(TEAM.find(u=>u.id==='outsider'),ENCOUNTER),false);assert.equal(canAccess(TEAM.find(u=>u.role==='quality'),ENCOUNTER),false);
 const f=evaluate(await demoSources(),cutoff)[0];assert.equal(canDecide(TEAM[1],ENCOUNTER,f),false);
 assert.throws(()=>decide([f],f.id,TEAM[1],'resolved','done','lee'),/cannot decide/);
 assert.equal(canAccess({...TEAM[0],role:'admin'},ENCOUNTER),false);
});
test('test_log_and_redaction_safety: source unchanged, explicit mapping, allowlist rejects clinical strings',()=>{
 const raw='Jane Doe S1234567A jane@example.com +65 8123 4567 MRN: AB1234 900101-01-1234';const r=redact(raw,['Jane Doe']);
 for(const value of ['Jane Doe','S1234567A','jane@example.com','8123 4567','AB1234','900101-01-1234'])assert.ok(!r.text.includes(value),value);
 assert.equal(raw,'Jane Doe S1234567A jane@example.com +65 8123 4567 MRN: AB1234 900101-01-1234');
 r.mapping.forEach(m=>assert.equal(r.text.slice(m.redactedStart,m.redactedEnd),m.token));
 assert.throws(()=>auditMetadata(raw,'import','allowed',cutoff));assert.deepEqual(Object.keys(auditMetadata('lee','import','allowed',cutoff)),['actor','action','outcome','time']);
});
test('test_grounding: every flag, summary claim and exported decision resolves immutable evidence',async()=>{
 const ss=await demoSources(),fs=evaluate(ss,cutoff);for(const f of fs)f.evidence.forEach(e=>resolve(ss,e));
 const out=summary(ss,fs,cutoff,cutoff);out.claims.forEach(c=>c.evidence.forEach(e=>resolve(ss,e)));assert.match(exportSummary(out,ss),/SHA-256/);
 const bad={...fs[0].evidence[0],quote:'invented'};assert.throws(()=>resolve(ss,bad));
});
test('test_differencing: changed/copy-forward text is a review question, never a contradiction alone',async()=>{
 const a=await make('Mobilised with assistance.');
 for(const text of ['Mobilised independently.',a.text]){
 const b=await make(text,{version:2,time:'2026-09-22T02:00:00Z'}),fs=evaluate([a,b],cutoff);
 assert.equal(fs.length,1);assert.equal(fs[0].tier,3);assert.equal(fs[0].evidence.length,2);assert.equal(fs[0].category,text===a.text?'copied-forward':'version-change');
 }
});
test('test_question_bubble_grounding: bounded states, cutoff and incomplete extraction',async()=>{
 const ss=await demoSources(),fs=evaluate(ss,cutoff);let a=answerQuestion('ecg',ss,fs,cutoff);assert.equal(a.status,'not documented in supplied sources');assert.equal(a.checkedVersions.length,6);assert.ok(!JSON.stringify(a).includes('did not happen'));
 a=answerQuestion('ecg',[...ss,await responseSource()],fs,cutoff);assert.equal(a.status,'documented');assert.ok(a.evidence.length);
 const pdf=await make('',{type:'pdf',extraction:'unreadable'});assert.equal(answerQuestion('ecg',[...ss,pdf],fs,cutoff).status,'incomplete extraction');
 const neg=await make('ECG not performed');assert.equal(answerQuestion('ecg',[neg],[],cutoff).status,'not documented in supplied sources');
});
test('acceptance, edit and reassignment do not clear closure blockers; decision history survives rerun',async()=>{
 const ss=await demoSources();let fs=evaluate(ss,cutoff),f=fs.find(f=>f.tier===1);const count=blocking(fs).length;
 for(const action of ['accepted','edited']){fs=decide(fs,f.id,TEAM[0],action,'Reviewed original, further confirmation needed.','lee',cutoff);assert.equal(blocking(fs).length,count);}
 fs=reconcile(fs,evaluate(ss,cutoff));assert.equal(fs.find(x=>x.id===f.id).history.length,2);
 assert.throws(()=>decide(fs,f.id,TEAM[0],'resolved','','lee'),/rationale/);assert.throws(()=>decide(fs,f.id,TEAM[0],'edited','Transfer','tan'),/clinician/);
 fs=decide(fs,f.id,TEAM[0],'resolved','Clinician confirmed completed work against source.','lee',cutoff);assert.equal(blocking(fs).length,count-1);
});
test('versions immutable, duplicate intake idempotent, changed metadata rejects version reuse',async()=>{
 const a=await make('NKDA'),b=await make('NKDA');assert.equal(addSource([a],b).length,1);assert.throws(()=>{a.text='other';});
 assert.throws(()=>addSource([a],{...b,text:'Penicillin allergy'}),/different/);assert.throws(()=>addSource([a],{...b,owner:'tan'}),/different/);
});
test('cutoff excludes later arrival, higher version wins without destroying old provenance',async()=>{
 const a=await make('NKDA'),b=await make('Allergy: penicillin',{version:2});assert.equal(currentSources([a,b],cutoff)[0].version,2);assert.equal(resolve([a,b],span(a,0,4)).text,'NKDA');
 assert.equal(currentSources([a], '2026-09-22T05:00:00.000Z').length,0);
});
test('invalid source identity, author/discipline and empty text rejected',async()=>{
 for(const extra of [{owner:'outsider'},{discipline:'pharmacy'},{version:0},{encounter:'enc-other'},{text:''}])await assert.rejects(make('NKDA',extra));
});
test('human clarification preserves generated reason, evidence and decision history',async()=>{
 const ss=await demoSources(),fs=evaluate(ss,cutoff),f=fs.find(f=>f.tier===1);
 const next=decide(fs,f.id,TEAM[0],'edited','Clarified after reviewing both sources.','lee',cutoff,'useful','Awaiting confirmation from the original author.').find(x=>x.id===f.id);
 assert.equal(next.reason,f.reason);assert.deepEqual(next.evidence,f.evidence);assert.match(next.clarification,/original author/);assert.equal(next.history[0].clarification,next.clarification);assert.equal(blocking([next]).length,1);
 assert.match(exportSummary(summary(ss,[next],cutoff),ss),/Human clarification/);
});
test('cutoff handles timezone offsets by instant, not lexical order',async()=>{
 const a=await make('NKDA');assert.equal(currentSources([a],'2026-09-22T13:00:00+08:00').length,0);assert.equal(currentSources([a],'2026-09-22T15:00:00+08:00').length,1);
});
