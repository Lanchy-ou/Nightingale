import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
await mkdir('test-results',{recursive:true});
const video=await readFile('output/Noteguard_Demo.webm');
const server=createServer((req,res)=>{
 const range=req.headers.range?.match(/bytes=(\d+)-(\d*)/),start=range?Number(range[1]):0,end=range&&range[2]?Number(range[2]):video.length-1;
 res.writeHead(range?206:200,{'Content-Type':'video/webm','Content-Length':end-start+1,'Accept-Ranges':'bytes','Cache-Control':'no-store',...(range?{'Content-Range':`bytes ${start}-${end}/${video.length}`}:{})});res.end(video.subarray(start,end+1));
});
await new Promise(r=>server.listen(5180,'127.0.0.1',r));
const context=await chromium.launchPersistentContext(resolve('tmp/pwa-check'),{channel:process.env.NG_BROWSER||'msedge',headless:true,viewport:{width:1440,height:1000}});
try{
 const page=await context.newPage();await page.goto('http://127.0.0.1:5178/');await page.evaluate(()=>navigator.serviceWorker.ready);
 const cdp=await context.newCDPSession(page);const pwa=await cdp.send('Page.getInstallabilityErrors');
 if(pwa.installabilityErrors.length)throw Error(JSON.stringify(pwa));
 await page.goto('http://127.0.0.1:5180/');await page.locator('video').waitFor();
 await page.waitForFunction(()=>Number.isFinite(document.querySelector('video').duration));
 const duration=await page.locator('video').evaluate(v=>v.duration);if(duration>180||duration<30)throw Error('Unexpected video duration '+duration);
 for(const t of [12,40,65]){
  await page.locator('video').evaluate(async(v,t)=>{v.muted=true;await v.play();await new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=t;});await new Promise(resolve=>v.requestVideoFrameCallback(resolve));v.pause();},t);
  await page.screenshot({path:resolve(`test-results/video-${t}.png`)});
 }
 await writeFile('test-results/media-results.json',JSON.stringify({videoSeconds:duration,playback:'PASS',pwa:pwa.installabilityErrors},null,2));
 console.log(JSON.stringify({videoSeconds:duration,playback:'PASS',installabilityErrors:pwa.installabilityErrors}));
}finally{await context.close();server.close();}
