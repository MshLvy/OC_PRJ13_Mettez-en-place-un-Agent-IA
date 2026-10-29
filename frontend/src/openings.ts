import {State} from './game';
export type OpeningStatus='identified'|'family_only'|'unknown'|'ambiguous'|'catalog_unavailable';
export interface OpeningCandidate {eco:string;full_name:string;family:string;variation:string|null;source_file:string;source_line:number}
export interface OpeningReference {source:string;revision:string;license:'CC0-1.0';rows:number;positions:number;ambiguous_positions:number;index_sha256:string;scope:'all_rows_a_to_e_at_pinned_revision'}
export interface OpeningContext {fen:string;history:string[];family:string|null;eco:string|null;variation:string|null;source:'lichess_chess_openings_local';reference_revision:string|null;certainty:OpeningStatus;is_current_match:boolean;last_matched_ply:number|null}
export interface Opening {status:OpeningStatus;family:string|null;variation:string|null;full_name:string|null;eco:string|null;display_family:string|null;language:'fr'|'en'|'mixed'|null;last_matched_ply:number|null;matched_position_fen:string|null;position_fen:string;revision:number;snapshot:string;is_current_match:boolean;off_line_since_ply:number|null;possible_candidates:OpeningCandidate[];candidate_count:number;candidates_truncated:boolean;reference_revision:string|null;reference:OpeningReference|null;context:OpeningContext}
export type OpeningApi=(history:string[],signal:AbortSignal)=>Promise<unknown>;
export const openingApi:OpeningApi=async(history,signal)=>{
 const r=await fetch('/api/v1/openings/identify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({history}),signal});
 if(!r.ok)throw new Error('OPENING_UNAVAILABLE');return r.json();
};
function require(v:unknown):asserts v {if(!v)throw new Error('OPENING_INCONSISTENT');}
function text(v:unknown){return v===null||(typeof v==='string'&&v.length>0&&v.length<=256);}
export function validateOpening(value:unknown,p:State):Opening {
 const d=value as Opening;require(d&&['identified','family_only','unknown','ambiguous','catalog_unavailable'].includes(d.status));
 require(d.position_fen===p.fen&&d.revision===p.history.length&&d.snapshot===p.snapshot&&typeof d.is_current_match==='boolean');
 const c=d.context;require(c&&c.fen===p.fen&&Array.isArray(c.history)&&c.history.length===p.history.length&&c.history.every((m,i)=>m===p.history[i])&&c.source==='lichess_chess_openings_local'&&c.certainty===d.status&&c.reference_revision===d.reference_revision&&c.family===d.family&&c.eco===d.eco&&c.variation===d.variation&&c.is_current_match===d.is_current_match&&c.last_matched_ply===d.last_matched_ply);
 require([d.family,d.variation,d.full_name,d.display_family].every(text)&&[null,'fr','en','mixed'].includes(d.language));
 require(d.eco===null||/^[A-E][0-9]{2}$/.test(d.eco));
 const known=d.status==='identified'||d.status==='family_only'||d.status==='ambiguous';
 if(known){
  require(Number.isInteger(d.last_matched_ply)&&d.last_matched_ply!>=1&&d.last_matched_ply!<=p.history.length);
  const expectedFen=p.played[d.last_matched_ply!-1]?.fen_after;require(d.matched_position_fen===expectedFen);
  require(d.is_current_match===(d.last_matched_ply===p.history.length)&&d.off_line_since_ply===(d.is_current_match?null:d.last_matched_ply!+1));
  if(d.status!=='ambiguous')require(d.family&&d.display_family&&d.eco&&d.full_name&&d.language);
  if(d.status==='family_only')require(d.variation===null);
  if(d.status==='identified')require(d.variation!==null);
  if(d.status==='ambiguous')require(d.full_name===null&&d.variation===null&&d.candidate_count>1);
 }else require(d.last_matched_ply===null&&d.matched_position_fen===null&&!d.is_current_match&&d.off_line_since_ply===null&&d.family===null&&d.variation===null&&d.full_name===null&&d.eco===null&&d.display_family===null&&d.language===null);
 require(Array.isArray(d.possible_candidates)&&d.possible_candidates.length<=8&&Number.isSafeInteger(d.candidate_count)&&d.candidate_count>=0&&d.possible_candidates.length===Math.min(d.candidate_count,8)&&d.candidates_truncated===(d.candidate_count>8));
 require(known?d.candidate_count>0:d.candidate_count===0);
 for(const item of d.possible_candidates)require(item&&/^[A-E][0-9]{2}$/.test(item.eco)&&typeof item.full_name==='string'&&item.full_name.length>0&&item.full_name.length<=256&&typeof item.family==='string'&&item.family.length>0&&item.family.length<=256&&text(item.variation)&&/^[a-e]\.tsv$/.test(item.source_file)&&Number.isSafeInteger(item.source_line)&&item.source_line>=2);
 require(new Set(d.possible_candidates.map(x=>x.eco+'|'+x.full_name)).size===d.possible_candidates.length);
 if(d.status==='identified'||d.status==='family_only'){const item=d.possible_candidates[0];require(d.candidate_count===1&&item.eco===d.eco&&item.full_name===d.full_name&&item.family===d.family&&item.variation===d.variation);}
 if(d.status==='ambiguous')require(d.possible_candidates.every(item=>(d.family===null||item.family===d.family)&&(d.eco===null||item.eco===d.eco)));
 if(d.status==='catalog_unavailable')require(d.reference===null&&d.reference_revision===null);
 else {const r=d.reference;require(r&&r.source==='https://github.com/lichess-org/chess-openings'&&r.license==='CC0-1.0'&&/^[a-f0-9]{40}$/.test(r.revision)&&r.revision===d.reference_revision&&r.scope==='all_rows_a_to_e_at_pinned_revision'&&Number.isSafeInteger(r.rows)&&r.rows>0&&r.rows<=10000&&Number.isSafeInteger(r.positions)&&r.positions>0&&r.positions<=r.rows&&Number.isSafeInteger(r.ambiguous_positions)&&r.ambiguous_positions>=0&&r.ambiguous_positions<=r.positions&&/^[a-f0-9]{64}$/.test(r.index_sha256));}
 return d;
}
export function openingStatus(status:OpeningStatus){return {identified:'Variante référencée',family_only:'Famille identifiée',unknown:'Ouverture non identifiée',ambiguous:'Plusieurs désignations possibles',catalog_unavailable:'Référentiel local indisponible'}[status];}
export function plyLabel(ply:number){return Math.ceil(ply/2)+(ply%2?' (Blancs)':'… (Noirs)')+' · demi-coup '+ply;}
export class OpeningPanel {
 data?:Opening;busy=false;error='';private position?:State;private generation=0;private abort?:AbortController;private activeKey='';private disposed=false;
 private cache?:{key:string;data:Opening};
 constructor(private request:OpeningApi=openingApi,private changed:()=>void=()=>{},private timeout=5000){}
 invalidate(){this.generation++;this.abort?.abort();this.abort=undefined;this.position=undefined;this.activeKey='';this.data=undefined;this.busy=false;this.error='';if(!this.disposed)this.changed();}
 dispose(){this.disposed=true;this.invalidate();}
 async accept(p:State){
  if(this.disposed)return;const key=p.snapshot+'|'+p.fen;this.position=p;if(key===this.activeKey)return;
  this.abort?.abort();const id=++this.generation;this.activeKey=key;this.data=undefined;this.error='';
  if(this.cache?.key===key){this.data=this.cache.data;this.busy=false;this.changed();return;}
  this.abort=new AbortController();const abort=this.abort;this.busy=true;this.changed();const timer=setTimeout(()=>abort.abort(),this.timeout);
  try {const raw=await this.request([...p.history],abort.signal);if(id!==this.generation||this.disposed)return;if(abort.signal.aborted)throw Error();
   const data=validateOpening(raw,p);this.data=data;this.cache={key,data};
  }catch{if(id===this.generation&&!this.disposed){this.data=undefined;this.error=abort.signal.aborted?'Identification locale trop longue ; réessayez explicitement.':'Identification absente ou incohérente avec la partie ; aucun nom conservé.';}}
  finally{clearTimeout(timer);if(id===this.generation&&!this.disposed){this.busy=false;this.changed();}}
 }
 retry(){if(!this.busy&&this.position){const p=this.position;this.activeKey='';this.cache=undefined;void this.accept(p);}}
 get context(){return this.data?.context;}
}
