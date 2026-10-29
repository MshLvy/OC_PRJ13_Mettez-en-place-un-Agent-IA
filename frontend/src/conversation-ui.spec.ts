import '@angular/compiler';
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
const s={history:[],revision:0,snapshot:'a'.repeat(64),fen:'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',turn:'white',legal_moves:['e2e4'],played:[],terminal:false,result:null,termination:null};
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
it('panneau Angular : clic explicite, sources lisibles et aucune génération inventée',async()=>{
 const fetch=vi.fn(async(url:string)=>({ok:true,json:async()=>url.includes('/conversation')?{status:'partial',reason:'GENERATION_DISABLED',message:'Extraits disponibles. Mistral désactivé.',fen:s.fen,snapshot:s.snapshot,retrieval_mode:'offline_bm25_v3',dense_status:'integration_pending',limits:['Revue humaine en attente'],generation:{status:'generation_disabled',model:'mistral-small-latest',executed:false,answer:null},passages:[{chunk_id:'v3e-sicilienne-presentation-01-c01',passage_id:'v3e-sicilienne-presentation-01',family:'sicilienne',text:'EXTRAIT DE TEST <script>non exécuté</script>',text_sha256:'b'.repeat(64),corpus_version:'pilot-fr-v3-enriched-0.1',license:'CC-BY-SA-4.0',attribution:'Contributeurs TEST',modification_notice:'Adaptation TEST',reference_fen:s.fen,scope:'current_reference_position',human_review:'pending',source_citations:[{id:'wb-test',url:'https://en.wikibooks.org/w/index.php?oldid=1',revid:1,work:'Wikibooks TEST',attribution:'Contributeurs TEST',license:'CC-BY-SA-4.0',license_url:'https://creativecommons.org/licenses/by-sa/4.0/'}]}]}:s}));
 vi.stubGlobal('fetch',fetch);TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();await vi.waitFor(()=>expect(f.componentInstance.g.state).toBeDefined());f.detectChanges();
 expect(fetch.mock.calls.filter(x=>x[0].includes('/conversation'))).toHaveLength(0);
 f.nativeElement.querySelector('.conversation-panel button').click();await f.whenStable();f.detectChanges();
 const panel=f.nativeElement.querySelector('.conversation-panel');expect(panel.textContent).toContain('Mistral désactivé');expect(panel.textContent).toContain('CC-BY-SA-4.0');expect(panel.textContent).toContain('Adaptation TEST');expect(panel.querySelector('article script')).toBeNull();expect(panel.querySelector('article a').href).toContain('oldid=1');
 f.componentInstance.c.invalidate();f.detectChanges();expect(panel.querySelector('article')).toBeNull();expect(panel.querySelector('button').disabled).toBe(true);
});
it('I08 exposes two explicit intentions without an automatic retrieval call',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>s}));vi.stubGlobal('fetch',fetch);
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();f.detectChanges();
 const select=f.nativeElement.querySelector('select[aria-label="Intention pédagogique"]') as HTMLSelectElement;
 expect(select.options).toHaveLength(2);expect(select.textContent).toContain('Comprendre une ouverture');
 select.value='opening_theory';select.dispatchEvent(new Event('change'));await f.whenStable();f.detectChanges();
 expect(f.componentInstance.c.intent).toBe('opening_theory');expect(f.nativeElement.querySelector('.conversation-panel').textContent).toContain('ne portent pas sur la position affichée');
 expect(fetch.mock.calls.filter((x:any)=>String(x[0]).includes('/conversation'))).toHaveLength(0);
});
it('I09 labels deterministic restitution and separates retrieval from generation',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>s}));vi.stubGlobal('fetch',fetch);
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();
 f.componentInstance.c.data={status:'partial',reason:'LOCAL_GENERATOR_UNAVAILABLE',message:'Restitution documentaire déterministe.',fen:s.fen,snapshot:s.snapshot,passages:[],retrieval_mode:'offline_bm25_v3',dense_status:'integration_pending',limits:[],generation:{status:'deterministic',provider:'deterministic',engine:'deterministic',model:'documentary-extracts-v1',reason:'local_generator_unavailable',duration_ms:2,executed:false,answer:null}};
 f.changeDetectorRef.markForCheck();f.detectChanges();const panel=f.nativeElement.querySelector('.conversation-panel');
 expect(panel.textContent).toContain('aucun LLM n’a rédigé');expect(panel.textContent).toContain('offline_bm25_v3');expect(panel.querySelector('.generation-provenance').textContent).toContain('deterministic');
 expect(fetch.mock.calls.filter((x:any)=>String(x[0]).includes('/conversation'))).toHaveLength(0);
});

it('Qwen diagnostics expose phase timings and safe validation code without inventing unavailable measurements',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>s}));vi.stubGlobal('fetch',fetch);
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();
 f.componentInstance.c.data={status:'abstain',reason:'GENERATION_REJECTED',message:'Réponse écartée.',fen:s.fen,snapshot:s.snapshot,passages:[],retrieval_mode:'offline_bm25_v3',dense_status:'integration_pending',limits:[],timings:{total_ms:123,retrieval_ms:20},generation:{status:'abstain',provider:'local_llm',engine:'llama.cpp',model:'qwen-TEST.gguf',executed:true,answer:null,reason:'GENERATION_OUTPUT_REJECTED',validation_code:'UNKNOWN_CITATION_ALIAS',timings:{prompt_ms:1,inference_http_ms:90,validation_ms:2}}};
 f.changeDetectorRef.markForCheck();f.detectChanges();const panel=f.nativeElement.querySelector('.conversation-panel');
 expect(panel.textContent).toContain('UNKNOWN_CITATION_ALIAS');expect(panel.textContent).toContain('Total backend : 123 ms');expect(panel.textContent).toContain('Retrieval : 20 ms');expect(panel.textContent).toContain('Génération HTTP : 90 ms');expect(panel.textContent).toContain('Serveur génération : n/d ms');
 expect(fetch.mock.calls.filter((x:any)=>String(x[0]).includes('/conversation'))).toHaveLength(0);
});

it('Groq provenance is displayed without a new provider selector',async()=>{
 const fetch=vi.fn(async()=>({ok:true,json:async()=>s}));vi.stubGlobal('fetch',fetch);
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();
 f.componentInstance.c.data={status:'unavailable',reason:'PROVIDER_UNAVAILABLE',message:'Fournisseur indisponible.',fen:s.fen,snapshot:s.snapshot,passages:[],retrieval_mode:'offline_bm25_v3',dense_status:'integration_pending',limits:[],generation:{status:'provider_unavailable',provider:'groq_api',engine:'Groq',model:'openai/gpt-oss-120b',requested_model:'openai/gpt-oss-120b',actual_model:null,reason:'PROVIDER_RATE_LIMITED',executed:true,answer:null}};
 f.changeDetectorRef.markForCheck();f.detectChanges();const panel=f.nativeElement.querySelector('.conversation-panel');expect(panel.querySelector('.generation-provenance').textContent).toContain('groq_api · Groq');expect(panel.textContent).toContain('openai/gpt-oss-120b');expect(panel.textContent).toContain('PROVIDER_RATE_LIMITED');
 expect(fetch.mock.calls.filter((x:any)=>String(x[0]).includes('/conversation'))).toHaveLength(0);
});
