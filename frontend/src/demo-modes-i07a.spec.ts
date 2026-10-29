import '@angular/compiler';
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
const fixture=JSON.parse(readFileSync('tests/fixtures/analysis-synthetic.json','utf8')).data;
const s={history:[],revision:0,snapshot:'a'.repeat(64),fen:fixture.fen_normalized,turn:'white',legal_moves:['e2e4'],played:[],terminal:false,result:null,termination:null};
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
async function render(engine='binary_present_not_probed'){
 const calls:{url:string;body:any}[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string,opts?:RequestInit)=>{
  const b=opts?.body?JSON.parse(opts.body as string):null;calls.push({url,body:b});let data:any;
  if(url.endsWith('/capabilities'))data={demo_enabled:true,allowed_modes:['simulation','live'],default_mode:'simulation',live_reasons:['EXPLORER_LIVE_NOT_ALLOWED','GAME_TOOLS_DISABLED'],explorer:'disabled',engine};
  else if(url.includes('/demo/analysis')){const copy=structuredClone(fixture);copy.tools.explorer.result.source_mode='synthetic_fixture';copy.tools.engine.result.source_mode='synthetic_fixture';data={demo_mode:'simulation',simulation:true,data:copy};}
  else if(url.includes('/analysis/orchestrate')){data=structuredClone(fixture);data.tools.explorer={requested:false,status:'not_requested',result:null};data.tools.engine.result.source_mode='local_engine';}
  else data=s;
  return {ok:true,status:200,json:async()=>data,headers:new Headers({'X-Demo-Test':'offline-wiring'})};
 }));
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await vi.waitFor(()=>expect(f.componentInstance.a.data).toBeDefined());f.detectChanges();return {f,calls};
}
it('Réel actif malgré ressources partielles, RAG et exclusions visibles',async()=>{
 const {f}=await render('binary_missing');const buttons=Array.from(f.nativeElement.querySelectorAll('button')) as HTMLButtonElement[];
 expect(buttons.find(x=>x.textContent==='Réel')!.disabled).toBe(false);
 expect(f.nativeElement.querySelector('.local-engine-panel button').disabled).toBe(true);
 expect(f.nativeElement.querySelector('.conversation-panel')).not.toBeNull();
 expect(f.nativeElement.textContent).toContain('Explorer les vidéos');
 expect(f.nativeElement.querySelector('.conversation-panel').textContent).toContain('Mistral API à la soumission explicite');
});
it('analyse locale uniquement au clic, source local_engine distincte et résultat invalidé',async()=>{
 const {f,calls}=await render();expect(calls.filter(x=>x.url.includes('/analysis/orchestrate'))).toHaveLength(0);
 f.nativeElement.querySelector('.local-engine-panel button').click();await vi.waitFor(()=>expect(f.componentInstance.localEngine.data).toBeDefined());f.detectChanges();
 const req=calls.filter(x=>x.url.includes('/analysis/orchestrate'));expect(req).toHaveLength(1);expect(req[0].body).toMatchObject({explorer_mode:'disabled',include_engine:true});
 expect(f.componentInstance.localEngine.data?.tools.engine.result?.source_mode).toBe('local_engine');
 expect(f.nativeElement.querySelector('.local-engine-panel').textContent).toContain('TEST DE CÂBLAGE — runner moteur simulé');
 f.componentInstance.g.cancel();f.detectChanges();expect(f.componentInstance.localEngine.data).toBeUndefined();expect(calls.filter(x=>x.url.includes('/analysis/orchestrate'))).toHaveLength(1);
});
