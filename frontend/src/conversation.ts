import {State} from './game';
export interface Evidence {chunk_id:string;passage_id:string;family:string;text:string;text_sha256:string;corpus_version:string;license:string;attribution:string;modification_notice:string;reference_fen:string;scope:string;human_review:string;source_citations:{id:string;url:string;revid:number;work:string;attribution:string;license:string;license_url:string}[]}
export interface Conversation {session_receipt?:string|null;timings?:Record<string,number|null>;status:'invalid'|'abstain'|'partial'|'unavailable'|'answered';reason:string;message:string;fen:string|null;snapshot:string|null;passages:Evidence[];retrieval_mode:'offline_bm25_v3'|'hybrid_bm25_bge_v3'|'bm25_fallback_v3';dense_status:'integration_pending'|'ready'|'unavailable';intent?:'position'|'opening_theory';retrieval_trace?:{dense_attempted:boolean;dense_reason:string;collection?:string;model?:string;revision?:string;dimension?:number;elapsed_ms:number};limits:string[];generation:GenerationResult}
export interface GenerationResult {timings?:Record<string,number|null>;validation_code?:string|null;status:'generation_disabled'|'provider_unavailable'|'abstain'|'test_double'|'generated'|'deterministic';model:string;executed:boolean;provider?:'none'|'local_llm'|'mistral_api'|'groq_api'|'deterministic';engine?:'llama.cpp'|'Mistral'|'Groq'|'deterministic'|null;requested_model?:string|null;actual_model?:string|null;reason?:string|null;error_code?:string|null;duration_ms?:number;test_transport?:boolean;usage?:{prompt_tokens:number;completion_tokens:number;total_tokens:number}|null;answer:null|{paragraphs:{text:string;citation_ids:string[]}[];moves_uci?:string[];scope?:'position'|'opening_theory'|null;abstain?:boolean}}
export interface Question {intent?:'position'|'opening_theory';question:string;fen:string;history:string[];snapshot:string;request_generation:boolean;demo_mode:'simulation'|'live'}
export type ConversationApi=(body:Question,signal:AbortSignal)=>Promise<unknown>;
export const conversationApi:ConversationApi=async(body,signal)=>{
 const r=await fetch('/api/v1/advisor/conversation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
 if(!r.ok)throw new Error('CONVERSATION_UNAVAILABLE');return r.json();
};
export function safeSource(url:string){try{const u=new URL(url);return u.protocol==='https:'&&u.hostname==='en.wikibooks.org'&&!u.username&&!u.password?url:null;}catch{return null;}}
export function validateConversation(value:unknown,position:State,intent:'position'|'opening_theory'='position',mode:'simulation'|'live'='simulation'):Conversation {
 const r=value as Conversation;
 if(!r||!['invalid','abstain','partial','unavailable','answered'].includes(r.status)||typeof r.message!=='string'||r.message.length>600||!['offline_bm25_v3','hybrid_bm25_bge_v3','bm25_fallback_v3'].includes(r.retrieval_mode)||!['integration_pending','ready','unavailable'].includes(r.dense_status)||!Array.isArray(r.limits)||!r.limits.every(x=>typeof x==='string'&&x.length<600)||!Array.isArray(r.passages)||r.passages.length>3)throw new Error('INVALID_CONVERSATION');
 if((r.intent??'position')!==intent)throw new Error('STALE_CONVERSATION_INTENT');
 if(r.retrieval_mode!=='offline_bm25_v3'){const t=r.retrieval_trace;if(!t||t.dense_attempted!==true||t.collection!=='p13_openings_bge_1024_v1'||t.model!=='BAAI/bge-m3'||t.revision!=='5617a9f61b028005a4858fdac845db406aefb181'||t.dimension!==1024||typeof t.dense_reason!=='string'||t.dense_reason.length>100||!Number.isFinite(t.elapsed_ms)||(r.retrieval_mode==='hybrid_bm25_bge_v3'?r.dense_status!=='ready':r.dense_status!=='unavailable'))throw new Error('INVALID_DENSE_PROVENANCE');}
 if(r.status!=='invalid'&&(r.fen!==position.fen||r.snapshot!==position.snapshot))throw new Error('STALE_CONVERSATION');
 for(const p of r.passages){if(!p||!/^v3e-[a-z0-9-]+$/.test(p.chunk_id)||typeof p.text!=='string'||p.text.length>6000||! /^[a-f0-9]{64}$/.test(p.text_sha256)||p.license!=='CC-BY-SA-4.0'||p.corpus_version!=='pilot-fr-v3-enriched-0.1'||p.scope!==(intent==='opening_theory'?'opening_theory':'current_reference_position')||p.human_review!=='pending'||typeof p.attribution!=='string'||typeof p.modification_notice!=='string'||!Array.isArray(p.source_citations)||!p.source_citations.length||p.source_citations.some(s=>!safeSource(s.url)||s.license!=='CC-BY-SA-4.0'))throw new Error('INVALID_CITATION');}
 const g=r.generation;
 if(!g||!['generation_disabled','provider_unavailable','abstain','test_double','generated','deterministic'].includes(g.status)||typeof g.model!=='string'||!(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$/.test(g.model)||(g.provider==='groq_api'&&g.model==='openai/gpt-oss-120b'))||typeof g.executed!=='boolean')throw new Error('INVALID_GENERATION');
 if(g.duration_ms!==undefined&&(!Number.isFinite(g.duration_ms)||g.duration_ms<0))throw new Error('INVALID_GENERATION');
 if(g.usage){const u=g.usage;if(![u.prompt_tokens,u.completion_tokens,u.total_tokens].every(n=>Number.isSafeInteger(n)&&n>=0&&n<=10000000)||u.total_tokens!==u.prompt_tokens+u.completion_tokens)throw new Error('INVALID_USAGE');}
 if((g.status==='generated'||g.status==='test_double')&&g.provider&&g.provider!=='none'){
  if(!(mode==='simulation'?g.provider==='local_llm'&&g.engine==='llama.cpp':g.provider==='mistral_api'&&g.engine==='Mistral'||g.provider==='groq_api'&&g.engine==='Groq'&&g.requested_model==='openai/gpt-oss-120b'&&g.actual_model==='openai/gpt-oss-120b')||!g.requested_model||!g.actual_model||g.model!==g.actual_model||!g.executed||!g.answer)throw new Error('INVALID_GENERATION_PROVENANCE');
 }
 if(g.status==='generated'&&(!g.provider||g.provider==='none'||g.test_transport===true))throw new Error('UNLABELLED_GENERATION');
 if(g.status==='deterministic'&&(mode!=='simulation'||g.provider!=='deterministic'||g.engine!=='deterministic'||g.model!=='documentary-extracts-v1'||g.answer!==null||g.reason!=='local_generator_unavailable'))throw new Error('FALSE_LOCAL_GENERATION');
 if(!['test_double','generated'].includes(g.status)&&g.answer!==null)throw new Error('UNLABELLED_GENERATION');
 if(g.status==='generation_disabled'&&g.executed||r.status==='answered'&&(!['test_double','generated'].includes(g.status)||!g.answer))throw new Error('UNLABELLED_GENERATION');
 if(g.answer){const ids=new Set(r.passages.map(x=>x.chunk_id));if(!Array.isArray(g.answer.paragraphs)||g.answer.paragraphs.length<1||g.answer.paragraphs.length>3||g.answer.paragraphs.some(p=>typeof p.text!=='string'||p.text.length>1600||!Array.isArray(p.citation_ids)||!p.citation_ids.length||p.citation_ids.some(id=>!ids.has(id))))throw new Error('FABRICATED_CITATION');
  if(g.status==='generated'&&g.answer.scope!==intent)throw new Error('INVALID_GENERATION_SCOPE');
  if(g.answer.moves_uci&&(!Array.isArray(g.answer.moves_uci)||g.answer.moves_uci.length>8||g.answer.moves_uci.some(m=>!/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(m))||intent==='opening_theory'&&g.answer.moves_uci.length))throw new Error('INVALID_GENERATED_MOVES');
 }

 return r;
}
export class ConversationPanel {
 intent:'position'|'opening_theory'='position';
 setIntent(intent:'position'|'opening_theory'){if(!['position','opening_theory'].includes(intent)||intent===this.intent)return;const p=this.position;this.invalidate();this.intent=intent;if(p)this.accept(p);}
 question='Pourquoi le pion c5 contrôle d4 dans la Sicilienne ?';data?:Conversation;busy=false;error='';position?:State;
 private ticket=0;private abort?:AbortController;private disposed=false;
 constructor(private request:ConversationApi=conversationApi,private changed:()=>void=()=>{},private timeout=65000){}
 invalidate(){this.ticket++;this.abort?.abort();this.position=undefined;this.data=undefined;this.busy=false;this.error='';if(!this.disposed)this.changed();}
 accept(p:State){this.invalidate();this.position={...p,history:[...p.history]};}
 dispose(){this.disposed=true;this.invalidate();}
 async ask(mode:'simulation'|'live'){
  if(this.disposed||this.busy||!this.position||!this.question.trim()||this.question.length>600)return;
  const p=this.position,intent=this.intent,id=++this.ticket;this.abort=new AbortController();const abort=this.abort;this.data=undefined;this.error='';this.busy=true;this.changed();const timer=setTimeout(()=>abort.abort(),this.timeout);
  try{const value=await this.request({intent,question:this.question.trim(),fen:p.fen,history:[...p.history],snapshot:p.snapshot,request_generation:true,demo_mode:mode},abort.signal);
   if(id!==this.ticket||this.disposed)return;if(abort.signal.aborted)throw new Error('TIMEOUT');this.data=validateConversation(value,p,intent,mode);
  }catch{if(id===this.ticket&&!this.disposed)this.error=abort.signal.aborted?'Délai dépassé. Réessayez explicitement.':'Conseiller indisponible ou réponse incohérente ; aucun conseil ajouté.';
  }finally{clearTimeout(timer);if(id===this.ticket&&!this.disposed){this.busy=false;this.changed();}}
 }
}
