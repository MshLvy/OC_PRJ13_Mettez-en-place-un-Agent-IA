import '@angular/compiler';
import {afterEach,beforeAll,describe,it,expect,vi} from 'vitest';
import {readFileSync} from 'node:fs';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
const fixture=JSON.parse(readFileSync('tests/fixtures/analysis-synthetic.json','utf8'));
const initial={history:[],revision:0,snapshot:'a'.repeat(64),fen:fixture.data.fen_normalized,turn:'white',legal_moves:['e2e4'],played:[],terminal:false,result:null,termination:null};
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
async function render(change?:(data:any)=>void){
 let calls=0;
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>{const data=structuredClone(fixture.data);if(change)change(data);calls++;if(url.includes('/demo/capabilities'))return {ok:true,json:async()=>({demo_enabled:false,allowed_modes:[],default_mode:'simulation',live_reasons:[]}),headers:new Headers()};return {ok:true,json:async()=>url.includes('/analysis/')?data:initial,headers:new Headers({'X-Analysis-Simulation':'j06_i02_offline'})}}));
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);
 // Opt-in de test avant l'acceptation de la position, pas un défaut de l'application.
 f.componentInstance.a.policy={explorer:'synthetic_fixture',engine:true};f.detectChanges();await vi.waitFor(()=>expect(f.componentInstance.a.data).toBeDefined());f.detectChanges();return {f,calls:()=>calls};
}
describe('Panneau Angular avec réponse API synthétique',()=>{
 it('affiche comptes, fréquence, score cp, perspective et simulation',async()=>{const {f}=await render();const t=f.nativeElement.textContent;expect(t).toContain('60.0 %');expect(t).toContain('6 / 2 / 2');expect(t).toContain('+0.35 pion(s)');expect(t).toContain('perspective Blancs');expect(t).toContain('SIMULATION DE TEST');expect(t).toContain('base masters');});
 it('panne moteur ne masque pas théorie et ne garde pas de score',async()=>{const {f}=await render(d=>{d.status='partial';d.tools.engine.status='error';d.tools.engine.result=null;d.errors=[{tool:'engine',code:'STOCKFISH_UNAVAILABLE',http_status:503}];});expect(f.nativeElement.textContent).toContain('STOCKFISH_UNAVAILABLE');expect(f.nativeElement.querySelectorAll('tbody tr').length).toBe(2);expect(f.nativeElement.querySelector('.engine-score')).toBeNull();});
 it('panne Explorer ne masque pas score moteur',async()=>{const {f}=await render(d=>{d.status='partial';d.tools.explorer.status='error';d.tools.explorer.result=null;d.errors=[{tool:'explorer',code:'UPSTREAM_RATE_LIMITED',http_status:503}];});expect(f.nativeElement.textContent).toContain('UPSTREAM_RATE_LIMITED');expect(f.nativeElement.querySelector('.engine-score').textContent).toContain('+0.35');});
 it('redraw et sélection de case ne relancent pas l’analyse',async()=>{const {f,calls}=await render();const count=calls();f.detectChanges();f.componentInstance.g.square('e2');f.detectChanges();await Promise.resolve();expect(calls()).toBe(count);});
});
