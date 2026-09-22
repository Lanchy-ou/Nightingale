import {source, ENCOUNTER} from './core.mjs';
export const DEMO_RECORDS = [
  ['medical','lee','clinician','09:00','NKDA\nAmlodipine 5 mg oral daily\nAssessment recorded for this synthetic encounter.'],
  ['nursing','tan','nursing','10:00','Potassium 6.4 mmol/L\nAllergy: penicillin\nPatient reports previous rash with penicillin.'],
  ['pharmacy','patel','pharmacy','10:15','Amlodipine 10 mg oral daily\nMedication list requires reconciliation.'],
  ['physio','chen','physiotherapy','10:30','Mobilised with assistance.\nFurther mobility review requested.'],
  ['social','lim','counselling/social work','10:45','Family support discussed.\nTransport arrangements documented with the patient.'],
  ['followup','wong','other','11:00','Pending blood culture result\nReport not yet attached.'],
];
export async function demoSources() {
  return Promise.all(DEMO_RECORDS.map(([sourceId,owner,discipline,time,text])=>source({sourceId,owner,discipline,time:`2026-09-22T${time}:00+08:00`,text,encounter:ENCOUNTER.id,namespace:'synthetic',version:1,type:'text'},'2026-09-22T04:00:00.000Z')));
}
export async function responseSource() {
  return source({sourceId:'response',owner:'lee',discipline:'clinician',time:'2026-09-22T13:00:00+08:00',text:'Potassium reviewed; repeat sample requested.\nAllergy reconciled: penicillin allergy confirmed\nFollow-up for blood culture result; owner: lee; due: 2026-09-23T14:00:00+08:00\nAmlodipine dose changed from 5 mg to 10 mg oral daily\nECG performed at 12:30.',encounter:ENCOUNTER.id,namespace:'synthetic',version:1,type:'text'},'2026-09-22T05:01:00.000Z');
}
