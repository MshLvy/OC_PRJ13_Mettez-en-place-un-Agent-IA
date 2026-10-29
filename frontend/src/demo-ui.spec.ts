import '@angular/compiler';
import {afterEach,beforeAll,describe,it,expect,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
const fixture=JSON.parse(readFileSync('tests/fixtures/analysis-synthetic.json','utf8')).data;
const initial={history:[],revision:0,snapshot:'a'.repeat(64),fen:fixture.fen_normalized,turn:'white',legal_moves:['e2e4'],played:[],terminal:false,result:null,termination:null};
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
async function render(enabled=true,live=true){
 const requests:{url:string;body:any}[]=[];
 vi.stubGlobal('fetch',vi.fn(async(url:string,opts?:RequestInit)=>{
  const b=opts?.body?JSON.parse(opts.body as string):null;requests.push({url,body:b});let data:any;
  if(url.includes('capabilities'))data={demo_enabled:enabled,allowed_modes:enabled?(live?['simulation','live']:['simulation']):[],default_mode:'simulation',live_reasons:live?[]:['DEMO_LIVE_DISABLED'],explorer:'authorized_not_probed',engine:'binary_missing'};
  else if(url.includes('/demo/analysis')){const d=structuredClone(fixture);d.tools.explorer.result.source_mode=b.demo_mode==='live'?'live':'synthetic_fixture';d.tools.engine.result.source_mode=b.demo_mode==='live'?'local_engine':'synthetic_fixture';data={demo_mode:b.demo_mode,simulation:b.demo_mode==='simulation',data:d};}
  else if(url.includes('/analysis/')){data=structuredClone(fixture);data.tools.explorer={requested:false,status:'not_requested',result:null};data.tools.engine={requested:false,status:'not_requested',result:null};}
  else data=initial;
  return {ok:true,status:200,json:async()=>data,headers:new Headers()};
 }));
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await vi.waitFor(()=>expect(f.componentInstance.a.data).toBeDefined());f.detectChanges();return {f,requests};
}
describe('Commande Angular globale',()=>{
 it('un seul sélecteur, simulation par défaut, trois sources cohérentes',async()=>{const {f,requests}=await render();expect(f.nativeElement.querySelector('[aria-label="Simulation ou Réel"]')).not.toBeNull();expect(f.nativeElement.querySelector('[aria-label="Mode analyse Lichess"]')).toBeNull();expect(f.nativeElement.querySelector('.analysis-panel input[type="checkbox"]')).toBeNull();expect(f.nativeElement.textContent).toContain('DONNÉES FICTIVES');expect(f.nativeElement.textContent).toContain('+0.35');expect(requests.some(r=>r.body?.demo_mode==='live')).toBe(false);});
 it('sélecteur masqué en distribution',async()=>{const {f}=await render(false);expect(f.nativeElement.querySelector('[aria-label="Simulation ou Réel"]')).toBeNull();expect(f.componentInstance.d.mode).toBe('simulation');expect(f.componentInstance.a.data?.tools.engine.status).toBe('not_requested');});
 it('réel désactivé si plafond serveur refuse',async()=>{const {f}=await render(true,false);const b=Array.from(f.nativeElement.querySelectorAll('button')).find((v:any)=>v.textContent==='Réel') as HTMLButtonElement;expect(b.disabled).toBe(true);expect(f.nativeElement.textContent).toContain('DEMO_LIVE_DISABLED');});
 it('clic Réel ouvre confirmation sans requête live, annuler conserve position',async()=>{const {f,requests}=await render();const state=f.componentInstance.g.state,count=requests.length;(Array.from(f.nativeElement.querySelectorAll('button')).find((v:any)=>v.textContent==='Réel') as HTMLButtonElement).click();f.detectChanges();expect(f.nativeElement.querySelector('[role="dialog"]')).not.toBeNull();expect(f.componentInstance.g.state).toBe(state);expect(requests.length).toBe(count);(Array.from(f.nativeElement.querySelectorAll('button')).find((v:any)=>v.textContent==='Garder la partie') as HTMLButtonElement).click();f.detectChanges();expect(f.nativeElement.querySelector('[role="dialog"]')).toBeNull();expect(requests.length).toBe(count);});
 it('confirmation nettoie puis consulte réel une fois, retour fixture explicite',async()=>{const {f,requests}=await render();f.componentInstance.d.propose('live');f.componentInstance.switchConfirmed();await vi.waitFor(()=>expect(f.componentInstance.a.data?.tools.explorer.result?.source_mode).toBe('live'));f.detectChanges();expect(f.nativeElement.textContent).toContain('Aucun repli synthétique');expect(requests.filter(r=>r.body?.demo_mode==='live').length).toBe(1);expect(f.componentInstance.g.source).toBe('theory_then_engine');f.componentInstance.d.propose('simulation');f.componentInstance.switchConfirmed();await vi.waitFor(()=>expect(f.componentInstance.a.data?.tools.engine.result?.source_mode).toBe('synthetic_fixture'));f.detectChanges();expect(f.componentInstance.g.source).toBe('synthetic_fixture');expect(f.nativeElement.textContent).toContain('DONNÉES FICTIVES');});
});
