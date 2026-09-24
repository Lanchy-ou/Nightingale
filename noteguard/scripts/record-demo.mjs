import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
await mkdir('output',{recursive:true});await mkdir('tmp/video',{recursive:true});
const browser=await chromium.launch({channel:process.env.NG_BROWSER||'msedge',headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},recordVideo:{dir:'tmp/video',size:{width:1440,height:1000}}});
const page=await context.newPage();
const chapters=[];
async function caption(title,text){
 chapters.push({title,text});
 await page.evaluate(({title,text})=>{document.querySelector('#demo-caption')?.remove();const div=document.createElement('div');div.id='demo-caption';Object.assign(div.style,{position:'fixed',bottom:'18px',left:'280px',right:'24px',zIndex:99,background:'#123e38',color:'white',padding:'18px 24px',borderRadius:'10px',boxShadow:'0 5px 25px #0003',fontFamily:'Segoe UI, sans-serif'});const strong=document.createElement('strong');strong.textContent=title;strong.style.cssText='font-size:18px;display:block;margin-bottom:6px';const span=document.createElement('span');span.textContent=text;span.style.cssText='font-size:15px;color:#e5ecd9';div.append(strong,span);document.body.append(div);},{title,text});
}
const hold=ms=>page.waitForTimeout(ms);
try{
 await page.goto('http://127.0.0.1:5178/');
 await caption('Noteguard | A second look at the supplied record','Independent synthetic demo. Browser memory only. No server login, no external AI, no automatic clinical decisions.');await hold(5500);
 await page.getByRole('button',{name:'Load synthetic encounter'}).click();await page.locator('.flag').first().waitFor();
 await caption('1 / Multidisciplinary record intake','Six records: clinician, nursing, pharmacy, physiotherapy, counselling/social work and other staff. Every source has an author, time and immutable version.');await hold(6000);
 await page.locator('[data-view="records"]').click();await caption('Source inventory, not a flattened summary','Clinical time and import time are distinct. Checks use the displayed source cutoff and retain prior versions for provenance.');await hold(4500);
 await page.locator('[data-view="review"]').click();await page.locator('[data-testid="flag-allergy-conflict"]').scrollIntoViewIfNeeded();
 await caption('2 / A conflict with both sides of the evidence','The deterministic check finds NKDA versus penicillin allergy. It asks the responsible clinician to reconcile the entries; it does not choose the truth.');await hold(5500);
 await page.locator('[data-testid="flag-allergy-conflict"] .evidence').last().click();
 await caption('Exact source, exact version','The quoted source text is highlighted. Source ID, version and checksum remain available. Original documentation is never overwritten.');await hold(5000);
 await page.getByRole('button',{name:'Close source',exact:true}).click();
 const pending=page.locator('[data-testid="flag-pending-followup"]');await pending.scrollIntoViewIfNeeded();
 await caption('3 / A follow-up gap','A pending culture has no recognised owner and deadline in the supplied text. The source-note owner receives the question. Absence of documentation is not absence of care.');await hold(6000);
 const critical=page.locator('[data-testid="flag-critical-observation"]');await critical.scrollIntoViewIfNeeded();await critical.locator('summary').click();await critical.locator('[name="rationale"]').fill('I accept responsibility. I will review the source and confirm the documented response.');
 await caption('4 / Human responsibility','Accepting a concern records ownership. It does not mean that the underlying work is complete. Tier 1 closure blockers remain visible.');await hold(4500);
 await critical.getByRole('button',{name:'Record decision'}).click();await page.locator('.closure').scrollIntoViewIfNeeded();await caption('Acceptance is not resolution','Two Tier 1 concerns still block closure after acceptance. Every decision has an actor, rationale and time.');await hold(4000);
 await page.getByRole('button',{name:'＋ Add later clinician response (demo)',exact:true}).click();await critical.scrollIntoViewIfNeeded();
 await caption('5 / New evidence changes the check, not the human decision','A later clinician response now exists. New candidate alerts are suppressed, but existing concerns wait for explicit human disposition.');await hold(6000);
 await critical.locator('summary').click();await critical.locator('[name="action"]').selectOption('superseded');await critical.locator('[name="rationale"]').fill('Reviewed the later clinician response source. The prior unacknowledged-observation concern is superseded.');await critical.getByRole('button',{name:'Record decision'}).click();await page.locator('.closure').scrollIntoViewIfNeeded();
 await caption('A recorded human decision releases one blocker','The remaining allergy question still needs human disposition. This is a reconciliation status, not permission to discharge.');await hold(4500);
 await page.getByRole('button',{name:'＋ Add record',exact:true}).click();await page.locator('[name="sourceId"]').fill('scanned-report');await page.locator('[name="type"]').selectOption('pdf');await page.locator('[name="pdf"]').setInputFiles(resolve('output/pdf/scanned-report.pdf'));await page.getByRole('button',{name:'Import & run checks'}).click();await page.getByText('Source retained in memory.',{exact:false}).waitFor();
 await caption('6 / PDF extraction limits are visible','The original scanned PDF is retained locally and labelled unreadable. A manual-review concern is created; the system never pretends the scan was fully read.');await hold(5500);
 await page.locator('[data-view="summary"]').click();await page.locator('.summary-sheet').scrollIntoViewIfNeeded();
 await caption('7 / Handover summary and deliberate export','The snapshot shows source cutoff, source timeline, unresolved priorities, accountable owners and decisions. Every derived concern links to its source.');await hold(6500);
 await page.getByRole('button',{name:'Export summary',exact:true}).click();
 await page.getByRole('button',{name:'Reset session',exact:true}).click();await caption('8 / Privacy boundary','Reset and refresh clear records, attachments and decisions. Nothing enters browser persistence or an external AI service. This demo is not production access control.');await hold(6000);
}finally{const video=page.video();await context.close();await video.saveAs(resolve('output/Noteguard_Demo.webm'));await browser.close();await writeFile('output/demo-chapters.json',JSON.stringify(chapters,null,2));}
console.log('Recorded output/Noteguard_Demo.webm');
