import {describe,it,expect,vi,afterEach} from 'vitest';
import {ConversationPanel,validateConversation,Conversation,safeSource,ConversationApi} from './conversation';
import {State} from './game';
const s:State={history:[],revision:0,snapshot:'a'.repeat(64),fen:'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',turn:'white',legal_moves:[],played:[],terminal:false,result:null,termination:null};
export function reply():Conversation{return {status:'partial',reason:'GENERATION_DISABLED',message:'Extraits documentaires. Mistral désactivé.',fen:s.fen,snapshot:s.snapshot,retrieval_mode:'offline_bm25_v3',dense_status:'integration_pending',limits:['Corpus expérimental'],generation:{status:'generation_disabled',model:'mistral-small-latest',executed:false,answer:null},passages:[{chunk_id:'v3e-sicilienne-presentation-01-c01',passage_id:'v3e-sicilienne-presentation-01',family:'sicilienne',text:'EXTRAIT DE TEST',text_sha256:'c'.repeat(64),corpus_version:'pilot-fr-v3-enriched-0.1',license:'CC-BY-SA-4.0',attribution:'Attribution de TEST',modification_notice:'Modification de TEST',reference_fen:s.fen,scope:'current_reference_position',human_review:'pending',source_citations:[{id:'wb-test',url:'https://en.wikibooks.org/w/index.php?oldid=1',work:'Wikibooks TEST',revid:1,attribution:'Contributeurs TEST',license:'CC-BY-SA-4.0',license_url:'https://creativecommons.org/licenses/by-sa/4.0/'}]}]};}
afterEach(()=>vi.useRealTimers());
describe('Conseiller : requête explicite et protection de position',()=>{
 it('aucun appel sur accept/invalidate, puis appel explicite sans doublon',async()=>{let resolve!:(x:unknown)=>void;const api=vi.fn((..._args:Parameters<ConversationApi>)=>new Promise(r=>resolve=r));const p=new ConversationPanel(api);p.accept(s);expect(api).not.toHaveBeenCalled();const first=p.ask('simulation');await p.ask('simulation');expect(api).toHaveBeenCalledTimes(1);expect(api.mock.calls[0][0]).toMatchObject({snapshot:s.snapshot,request_generation:true,demo_mode:'simulation'});resolve(reply());await first;expect(p.data?.passages).toHaveLength(1);expect(p.data?.generation.executed).toBe(false);});
 it('ignore une réponse tardive malgré transport ignorant abort',async()=>{let resolve!:(x:unknown)=>void;const p=new ConversationPanel(()=>new Promise(r=>resolve=r));p.accept(s);const pending=p.ask('simulation');p.accept({...s,snapshot:'b'.repeat(64)});resolve(reply());await pending;expect(p.data).toBeUndefined();expect(p.busy).toBe(false);});
 it('ignore aussi après changement de mode/reset et destruction',async()=>{let resolve!:(x:unknown)=>void;const p=new ConversationPanel(()=>new Promise(r=>resolve=r));p.accept(s);const request=p.ask('live');p.invalidate();p.dispose();resolve(reply());await request;expect(p.data).toBeUndefined();});
 it('refuse une FEN de réponse incohérente',async()=>{const p=new ConversationPanel(async()=>({...reply(),fen:'different'}));p.accept(s);await p.ask('simulation');expect(p.error).toContain('incohérente');expect(p.data).toBeUndefined();});
 it('expire sans retry automatique',async()=>{vi.useFakeTimers();let resolve!:(x:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new ConversationPanel(api,undefined,10);p.accept(s);const pending=p.ask('simulation');await vi.advanceTimersByTimeAsync(11);resolve(reply());await pending;expect(p.error).toContain('Délai');expect(api).toHaveBeenCalledTimes(1);});
 it('refuse citation malveillante et génération non identifiée',()=>{const r=reply();r.passages[0].source_citations[0].url='javascript:alert(1)';expect(()=>validateConversation(r,s)).toThrow();expect(safeSource('javascript:alert(1)')).toBeNull();const g=reply();g.generation.answer={paragraphs:[{text:'FAUX',citation_ids:['invented']}]};expect(()=>validateConversation(g,s)).toThrow();});
});

describe('I08 dense provenance and explicit pedagogical intent (synthetic responses)',()=>{
 it('accepts labelled hybrid but rejects an unverified revision',()=>{
  const r=reply();r.retrieval_mode='hybrid_bm25_bge_v3';r.dense_status='ready';r.retrieval_trace={dense_attempted:true,dense_reason:'BGE_READ_ONLY_SEARCH_VERIFIED',collection:'p13_openings_bge_1024_v1',model:'BAAI/bge-m3',revision:'5617a9f61b028005a4858fdac845db406aefb181',dimension:1024,elapsed_ms:12};
  expect(validateConversation(r,s).retrieval_mode).toBe('hybrid_bm25_bge_v3');r.retrieval_trace.revision='wrong';expect(()=>validateConversation(r,s)).toThrow('INVALID_DENSE_PROVENANCE');
 });
 it('invalidates an old position response when the intention changes',async()=>{
  let resolve!:(x:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new ConversationPanel(api);p.accept(s);const pending=p.ask('simulation');p.setIntent('opening_theory');resolve(reply());await pending;expect(p.data).toBeUndefined();expect(p.position?.snapshot).toBe(s.snapshot);expect(p.intent).toBe('opening_theory');
 });
 it('sends theory explicitly and checks scope instead of silently relaxing a position request',async()=>{
  const r=reply();r.intent='opening_theory';r.passages[0].scope='opening_theory';const api=vi.fn(async(..._args:Parameters<ConversationApi>)=>r);const p=new ConversationPanel(api);p.accept(s);p.setIntent('opening_theory');await p.ask('live');expect(api.mock.calls[0][0]).toMatchObject({intent:'opening_theory',demo_mode:'live'});expect(p.data?.passages[0].scope).toBe('opening_theory');expect(()=>validateConversation(r,s)).toThrow('STALE_CONVERSATION_INTENT');
 });
});

describe('I09 interchangeable generators, synthetic responses only',()=>{
 function generated(){const r=reply();r.status='answered';r.generation={status:'generated',provider:'local_llm',engine:'llama.cpp',model:'qwen-TEST.gguf',requested_model:'qwen-TEST.gguf',actual_model:'qwen-TEST.gguf',executed:true,test_transport:false,duration_ms:20,usage:{prompt_tokens:100,completion_tokens:20,total_tokens:120},answer:{scope:'position',paragraphs:[{text:'Paragraphe de TEST',citation_ids:[r.passages[0].chunk_id]}],moves_uci:[]}};return r;}
 it('requires the actual generator to match the selected mode',()=>{
  const r=generated();expect(validateConversation(r,s).generation.engine).toBe('llama.cpp');
  expect(()=>validateConversation(r,s,'position','live')).toThrow('INVALID_GENERATION_PROVENANCE');
  r.generation.provider='mistral_api';r.generation.engine='Mistral';r.generation.model=r.generation.actual_model='mistral-TEST';r.generation.requested_model='mistral-small-latest';
  expect(validateConversation(r,s,'position','live').generation.actual_model).toBe('mistral-TEST');
 });
 it('rejects a fake deterministic answer and never accepts deterministic fallback in live mode',()=>{
  const r=reply();r.generation={status:'deterministic',provider:'deterministic',engine:'deterministic',model:'documentary-extracts-v1',reason:'local_generator_unavailable',executed:false,answer:null};
  expect(validateConversation(r,s).generation.answer).toBeNull();expect(()=>validateConversation(r,s,'position','live')).toThrow('FALSE_LOCAL_GENERATION');
  r.generation.answer={paragraphs:[{text:'FAUX LLM',citation_ids:[r.passages[0].chunk_id]}]};expect(()=>validateConversation(r,s)).toThrow();
 });
 it('rejects inconsistent usage, fabricated citations and wrong theory scope',()=>{
  const r=generated();r.generation.usage!.total_tokens=999;expect(()=>validateConversation(r,s)).toThrow('INVALID_USAGE');
  r.generation.usage=null;r.generation.answer!.paragraphs[0].citation_ids=['invented'];expect(()=>validateConversation(r,s)).toThrow('FABRICATED_CITATION');
  r.generation.answer!.paragraphs[0].citation_ids=[r.passages[0].chunk_id];r.generation.answer!.scope='opening_theory';expect(()=>validateConversation(r,s)).toThrow('INVALID_GENERATION_SCOPE');
 });
 it('a mode/reset change still invalidates an in-flight generated response',async()=>{
  let resolve!:(r:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new ConversationPanel(api);p.accept(s);const pending=p.ask('simulation');p.invalidate();resolve(generated());await pending;expect(p.data).toBeUndefined();expect(api).toHaveBeenCalledTimes(1);
 });
});

describe('Groq explicit API provenance (doubles only)',()=>{
 function groq(){const r=reply();r.status='answered';r.generation={status:'generated',provider:'groq_api',engine:'Groq',model:'openai/gpt-oss-120b',requested_model:'openai/gpt-oss-120b',actual_model:'openai/gpt-oss-120b',executed:true,test_transport:false,answer:{scope:'position',paragraphs:[{text:'TEST sourcé',citation_ids:[r.passages[0].chunk_id]}],moves_uci:[]}};return r;}
 it('accepts allowlisted slash model only as Groq live, never Simulation',()=>{
  const r=groq();expect(validateConversation(r,s,'position','live').generation.engine).toBe('Groq');expect(()=>validateConversation(r,s)).toThrow('INVALID_GENERATION_PROVENANCE');
 });
 it('rejects mismatched engine, model and invented citations',()=>{
  const a=groq();a.generation.engine='Mistral';expect(()=>validateConversation(a,s,'position','live')).toThrow('INVALID_GENERATION_PROVENANCE');
  const b=groq();b.generation.model=b.generation.actual_model='evil/model';expect(()=>validateConversation(b,s,'position','live')).toThrow('INVALID_GENERATION');
  const c=groq();c.generation.answer!.paragraphs[0].citation_ids=['invented'];expect(()=>validateConversation(c,s,'position','live')).toThrow('FABRICATED_CITATION');
 });
});
