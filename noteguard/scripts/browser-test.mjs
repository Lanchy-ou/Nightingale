import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile,readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
const out=resolve('test-results');await mkdir(out,{recursive:true});
const browser=await chromium.launch({channel:process.env.NG_BROWSER||'msedge',headless:true});
const context=await browser.newContext({baseURL:'http://127.0.0.1:5178',viewport:{width:1440,height:1000},acceptDownloads:true});
const page=await context.newPage(),errors=[],external=[],posts=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(!r.url().startsWith('http://127.0.0.1:5178/')&&!r.url().startsWith('blob:')&&!r.url().startsWith('data:'))external.push(r.url());if(r.method()==='POST')posts.push(r.url());});
const results=[];
async function step(name,fn){await fn();results.push({name,status:'PASS'});console.log('PASS',name);}
try{
 await page.goto('http://127.0.0.1:5178/');
 await step('initial case empty; no clinical response caching',async()=>{await page.getByRole('heading',{name:'Start with the record, not a conclusion.'}).waitFor();const r=await page.request.get('/');assert.match(r.headers()['cache-control'],/no-store/);});
 await step('demo produces four grounded concerns, two closure blockers',async()=>{await page.getByRole('button',{name:'Load synthetic encounter'}).click();await page.locator('[data-testid="flag-critical-observation"]').waitFor();assert.equal(await page.locator('.flag').count(),4);assert.match(await page.locator('.closure').innerText(),/2 closure blockers/);});
 await page.screenshot({path:resolve(out,'desktop.png'),fullPage:true});
 await step('evidence reader highlights exact source',async()=>{await page.locator('[data-testid="flag-allergy-conflict"] .evidence').first().click();await page.getByRole('dialog').waitFor();assert.equal(await page.locator('mark').innerText(),'NKDA');await page.getByRole('button',{name:'Close source',exact:true}).click();});
 await step('acceptance does not clear Tier 1; rationale recorded',async()=>{const card=page.locator('[data-testid="flag-critical-observation"]');await card.locator('summary').click();await card.locator('[name="rationale"]').fill('Synthetic review: I accept responsibility; response still needs confirmation.');await card.getByRole('button',{name:'Record decision'}).click();assert.match(await page.locator('.closure').innerText(),/2 closure blockers/);assert.match(await page.locator('[data-testid="flag-critical-observation"] .status').innerText(),/accepted/i);});
 await step('new response changes applicability but never auto-closes',async()=>{await page.getByRole('button',{name:'＋ Add later clinician response (demo)',exact:true}).click();await page.getByText('Later response added.',{exact:false}).waitFor();assert.equal(await page.locator('.changed').count(),4);assert.match(await page.locator('.closure').innerText(),/2 closure blockers/);});
 await step('human supersession releases one blocker and keeps prior decisions',async()=>{const card=page.locator('[data-testid="flag-critical-observation"]');await card.locator('summary').click();await card.locator('[name="action"]').selectOption('superseded');await card.locator('[name="rationale"]').fill('Reviewed the later clinician response. Prior unacknowledged-observation concern is superseded.');await card.getByRole('button',{name:'Record decision'}).click();assert.match(await page.locator('.closure').innerText(),/1 closure blocker/);});
 await step('source-bounded ECG answer',async()=>{await page.getByRole('button',{name:'Is an ECG documented?',exact:true}).click();assert.equal((await page.locator('.answer strong').innerText()).toLowerCase(),'documented');await page.getByRole('button',{name:'Close question'}).click();});
 await step('summary exports immutable citations and rationale',async()=>{await page.locator('[data-view="summary"]').click();const download=page.waitForEvent('download');await page.getByRole('button',{name:'Export summary',exact:true}).click();const file=await download;await file.saveAs(resolve(out,'summary.txt'));const text=await readFile(resolve(out,'summary.txt'),'utf8');assert.match(text,/SHA-256/);assert.match(text,/Human review required/);assert.match(text,/superseded/);});
 for(const [filename,status] of [['selectable-report','complete'],['scanned-report','unreadable'],['partial-report','partial']]){
  await step(`real PDF intake: ${filename}`,async()=>{
   await page.getByRole('button',{name:'＋ Add record',exact:true}).click();await page.locator('[name="sourceId"]').fill(filename);await page.locator('[name="type"]').selectOption('pdf');await page.locator('[name="pdf"]').setInputFiles(resolve('output/pdf',filename+'.pdf'));await page.getByRole('button',{name:'Import & run checks'}).click();await page.getByText('Source retained in memory.',{exact:false}).waitFor();
   const record=page.locator('.record').filter({has:page.getByRole('heading',{name:filename+' v1',exact:true})});await record.waitFor();assert.match(await record.innerText(),status==='complete'?/Text available/:new RegExp(status));
   await record.getByRole('button',{name:'Read source ↗',exact:true}).click();await page.getByText('Original page rendered locally.',{exact:false}).waitFor();assert.ok(await page.locator('canvas').evaluate(c=>c.width>0));await page.screenshot({path:resolve(out,filename+'.png')});await page.getByRole('button',{name:'Close source',exact:true}).click();
  });
 }
 await step('PDF review concerns grounded to attachments',async()=>{await page.locator('[data-view="review"]').click();assert.equal(await page.locator('[data-testid="flag-extraction-review"]').count(),2);});
 await step('mobile review has no page overflow and source controls work',async()=>{await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));await page.screenshot({path:resolve(out,'mobile.png'),fullPage:true});await page.locator('.evidence').first().click();await page.getByRole('dialog').waitFor();await page.getByRole('button',{name:'Close source',exact:true}).click();});
 await step('no storage or external clinical egress',async()=>{const state=await page.evaluate(async()=>({local:localStorage.length,session:sessionStorage.length,caches:(await caches.keys()).length,dbs:(await indexedDB.databases()).length}));assert.deepEqual(state,{local:0,session:0,caches:0,dbs:0});assert.deepEqual(external,[]);assert.deepEqual(posts,[]);});
 await step('refresh clears the whole case and decisions',async()=>{await page.reload();await page.getByRole('heading',{name:'Start with the record, not a conclusion.'}).waitFor();assert.equal(await page.locator('.flag').count(),0);});
 await step('demo scope isolation and perspective switch clears evidence',async()=>{await page.getByRole('button',{name:'Load synthetic encounter'}).click();await page.locator('.flag').first().waitFor();await page.locator('#user').selectOption('outsider');await page.getByRole('heading',{name:'Encounter unavailable for this demo role'}).waitFor();assert.equal(await page.locator('.flag').count(),0);await page.locator('#user').selectOption('lee');await page.getByRole('heading',{name:'Start with the record, not a conclusion.'}).waitFor();});
 await step('no browser runtime errors',async()=>assert.deepEqual(errors,[]));
 await writeFile(resolve(out,'browser-results.json'),JSON.stringify({results,errors,external,posts},null,2));
}finally{await browser.close();}
