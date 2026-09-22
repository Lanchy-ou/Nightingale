export function redact(text, names = []) {
  const candidates=[];
  const collect = (regex,kind) => { for(const m of text.matchAll(regex)) candidates.push({start:m.index,end:m.index+m[0].length,kind}); };
  for (const name of names.filter(Boolean)) collect(new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi'),'NAME');
  collect(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,'EMAIL');
  collect(/\b[STFGM]\d{7}[A-Z]\b/gi,'ID');
  collect(/\b\d{6}-\d{2}-\d{4}\b/g,'ID');
  collect(/\b(?:MRN|ID|Passport)\s*[:#]\s*[A-Z0-9-]+/gi,'ID');
  collect(/(?:\+\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?){2,4}\d{3,4}\b/g,'PHONE');
  candidates.sort((a,b)=>a.start-b.start || b.end-a.end);
  let offset=0, output='',mapping=[];
  for(const c of candidates) {
    if(c.start<offset) continue;
    output+=text.slice(offset,c.start);
    const token=`[${c.kind}_${mapping.length+1}]`, redactedStart=output.length;
    output+=token;mapping.push({...c,redactedStart,redactedEnd:output.length,token});offset=c.end;
  }
  return {text:output+text.slice(offset),mapping};
}
// No clinical strings accepted. Kept in memory; this is not a durable audit stream.
export function auditMetadata(actor, action, outcome, time) {
  const actors=['lee','tan','patel','chen','lim','wong','quality','outsider'];
  const actions=['import','review','accepted','edited','dismissed','resolved','superseded','open','reset'];
  if(!actors.includes(actor)||!actions.includes(action)||!['allowed','denied'].includes(outcome)||!/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/.test(time)) throw Error('Invalid audit metadata.');
  return {actor,action,outcome,time};
}
