import * as pdfjs from 'pdfjs-dist';
import worker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
pdfjs.GlobalWorkerOptions.workerSrc = worker;
export function classifyPages(pageTexts) {
  let text='';
  const pages=pageTexts.map((value,i)=>{
    const start=text.length;
    text+=value+'\n';
    return {number:i+1,start,end:text.length,status:value.replace(/\s/g,'').length>=30?'complete':'needs_review'};
  });
  const complete=pages.filter(p=>p.status==='complete').length;
  return {text,pages,extraction:complete===pages.length?'complete':complete?'partial':'unreadable'};
}
export async function readPDF(bytes) {
  const task=pdfjs.getDocument({data:new Uint8Array(bytes.slice(0)),isEvalSupported:false,useSystemFonts:true,verbosity:0});
  let doc;
  try {
    doc=await task.promise;
    if(doc.numPages>50) throw Error('page-limit');
    const texts=[];
    for(let n=1;n<=doc.numPages;n++) {
      const page=await doc.getPage(n),content=await page.getTextContent();
      texts.push(content.items.map(item=>item.str+(item.hasEOL?'\n':' ')).join(''));
      page.cleanup();
    }
    return classifyPages(texts);
  } catch {
    return {text:'',pages:[{number:1,start:0,end:0,status:'needs_review'}],extraction:'unreadable'};
  } finally { await task.destroy(); }
}
export async function renderPDF(bytes,pageNumber,canvas) {
  const task=pdfjs.getDocument({data:new Uint8Array(bytes.slice(0)),isEvalSupported:false,useSystemFonts:true,verbosity:0});
  try {
    const doc=await task.promise,page=await doc.getPage(pageNumber),viewport=page.getViewport({scale:1.4});
    canvas.width=viewport.width;canvas.height=viewport.height;
    await page.render({canvasContext:canvas.getContext('2d'),viewport}).promise;
  } finally {await task.destroy();}
}
