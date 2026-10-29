import {State} from './game';
import {VideoOpening} from './videos';
export interface SavedExchange {question:string;answer:{paragraphs:{text:string;citation_ids:string[]}[];scope:string;moves_uci:string[]};intent:string;provider:string;engine:string;model:string;retrieval_mode:string;review:'application_checks_only_human_pending';citations:{chunk_id:string;text_sha256:string;license:string;corpus_version:string}[]}
export interface SessionSummary {id:string;opening:VideoOpening;created_at:string;updated_at:string}
export interface SessionRecord extends SessionSummary {schema_version:1;history:string[];fen:string;snapshot:string;exchanges:SavedExchange[]}
export type SessionsApi=(method:string,path:string,body:unknown,signal:AbortSignal)=>Promise<unknown>;
export const sessionsApi:SessionsApi=async(method,path,body,signal)=>{
 const r=await fetch('/api/v1/sessions'+path,{method,headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),signal});
 const data=await r.json();if(!r.ok)throw new Error(['SESSIONS_DISABLED','SESSION_RECEIPT_INVALID_OR_EXPIRED','INVALID_SESSION_REQUEST','SESSION_TOO_LARGE','SESSION_NOT_FOUND'].includes(data?.detail?.code)?data.detail.code:'SESSIONS_UNAVAILABLE');return data;
};
const id=(x:unknown)=>typeof x==='string'&&/^[a-f0-9]{32}$/.test(x);
const openings=['espagnole','italienne','sicilienne','francaise','caro_kann','gambit_dame'];
function summary(value:unknown):SessionSummary{const s=value as SessionSummary;if(!s||!id(s.id)||!openings.includes(s.opening)||typeof s.created_at!=='string'||s.created_at.length>40||!Number.isFinite(Date.parse(s.created_at))||typeof s.updated_at!=='string'||!Number.isFinite(Date.parse(s.updated_at)))throw Error();return s;}
function record(value:unknown):SessionRecord{
 const s=value as SessionRecord;summary(s);
 if(s.schema_version!==1||typeof s.fen!=='string'||s.fen.length>256||! /^[a-f0-9]{64}$/.test(s.snapshot)||!Array.isArray(s.history)||s.history.length>256||s.history.some(m=>! /^[a-h][1-8][a-h][1-8][qrbn]?$/.test(m))||!Array.isArray(s.exchanges)||s.exchanges.length>5)throw Error();
 for(const e of s.exchanges){if(!e||typeof e.question!=='string'||e.question.length>600||e.review!=='application_checks_only_human_pending'||!e.answer||!Array.isArray(e.answer.paragraphs)||e.answer.paragraphs.length>3||e.answer.paragraphs.some(p=>typeof p.text!=='string'||p.text.length>1600||!Array.isArray(p.citation_ids)||p.citation_ids.some(c=>! /^v3e-[a-z0-9-]{1,150}$/.test(c)))||!Array.isArray(e.citations)||e.citations.length>3)throw Error();}
 return s;
}
export class SessionsPanel {
 opening:VideoOpening|''='';includeAnswer=false;position?:State;items:SessionSummary[]=[];next:string|null=null;loaded?:SessionRecord;busy=false;message='Aucune sauvegarde automatique. Persistance locale optionnelle.';
 private ticket=0;private abort?:AbortController;private disposed=false;
 constructor(private api:SessionsApi=sessionsApi,private changed:()=>void=()=>{}){}
 invalidate(){this.ticket++;this.abort?.abort();this.busy=false;this.position=undefined;this.loaded=undefined;this.includeAnswer=false;if(!this.disposed)this.changed();}
 accept(s:State){this.invalidate();this.position={...s,history:[...s.history]};this.changed();}
 dispose(){this.disposed=true;this.invalidate();}
 private async run<T>(method:string,path:string,body:unknown,validate:(value:unknown)=>T):Promise<T|undefined>{
  if(this.busy||this.disposed)return;const ticket=++this.ticket;this.abort=new AbortController();const abort=this.abort;this.busy=true;this.message='Opération de séance en cours…';this.changed();const timer=setTimeout(()=>abort.abort(),5000);
  try{const raw=await this.api(method,path,body,abort.signal);if(this.disposed||ticket!==this.ticket)return;if(abort.signal.aborted)throw Error();const result=validate(raw);this.message='Opération confirmée.';return result;}
  catch(e){if(!this.disposed&&ticket===this.ticket)this.message=e instanceof Error&&e.message==='SESSIONS_DISABLED'?'Persistance désactivée. Le reste de l’atelier reste disponible.':e instanceof Error&&e.message==='SESSION_RECEIPT_INVALID_OR_EXPIRED'?'Réponse non enregistrée : reçu expiré ou contexte modifié. Décochez son inclusion pour sauvegarder la position seule.':e instanceof Error&&['INVALID_SESSION_REQUEST','SESSION_TOO_LARGE','SESSION_NOT_FOUND'].includes(e.message)?'Séance introuvable ou demande invalide ; aucune sauvegarde confirmée.':'Persistance indisponible ou résultat non confirmé. Consultez la liste avant de renvoyer une sauvegarde.';}
  finally{clearTimeout(timer);if(!this.disposed&&ticket===this.ticket){this.busy=false;this.changed();}}
 }
 setOpening(value:VideoOpening|''){const position=this.position;this.invalidate();this.position=position;this.opening=value;this.changed();}
 async save(receipt?:string|null){
  if(!this.position||!this.opening)return;const p=this.position;
  const body={opening:this.opening,fen:p.fen,history:[...p.history],snapshot:p.snapshot,receipts:this.includeAnswer&&receipt?[receipt]:[]};
  const epoch=this.ticket+1;const saved=await this.run('POST','',body,raw=>{const r=record(raw);if(r.fen!==p.fen||r.snapshot!==p.snapshot||JSON.stringify(r.history)!==JSON.stringify(p.history)||r.opening!==body.opening)throw Error();return r;});if(saved&&this.ticket===epoch&&!this.disposed){this.loaded=saved;this.message='Séance sauvegardée, confirmation du serveur reçue.';this.changed();}
 }
 async list(after:string|null=null){
  const epoch=this.ticket+1;const result=await this.run('GET','?limit=10'+(after?'&after='+after:''),undefined,raw=>{const r=raw as {items:unknown[];next_cursor:string|null};if(!r||!Array.isArray(r.items)||r.items.length>10||r.next_cursor!==null&&!id(r.next_cursor))throw Error();return {items:r.items.map(summary),next:r.next_cursor};});
  if(result&&this.ticket===epoch&&!this.disposed){this.items=result.items;this.next=result.next;this.changed();}
 }
 async consult(ident:string){if(!id(ident))return;const epoch=this.ticket+1;const saved=await this.run('GET','/'+ident,undefined,raw=>{const r=record(raw);if(r.id!==ident)throw Error();return r;});if(saved&&this.ticket===epoch&&!this.disposed){this.loaded=saved;this.changed();}return this.ticket===epoch&&!this.disposed?saved:undefined;}
 async remove(ident:string){if(!id(ident))return;const epoch=this.ticket+1;const result=await this.run('DELETE','/'+ident,undefined,raw=>{const r=raw as {status:string;id:string};if(r?.status!=='deleted'||r.id!==ident)throw Error();return r;});if(result&&this.ticket===epoch&&!this.disposed){this.items=this.items.filter(s=>s.id!==ident);if(this.loaded?.id===ident)this.loaded=undefined;this.message='Séance supprimée.';this.changed();}}
}
