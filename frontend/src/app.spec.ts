import '@angular/compiler';
import {afterEach,beforeAll,describe,it,expect,vi} from 'vitest';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
const initial={history:[],revision:0,snapshot:'a'.repeat(64),fen:'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',turn:'white',legal_moves:['e2e4'],played:[],terminal:false,result:null,termination:null};
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
async function render(){vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>initial})));TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();await vi.waitFor(()=>expect(f.componentInstance.g.state).toBeDefined());f.detectChanges();return f;}
describe('Composant Angular réel',()=>{
 it('64 boutons et les deux modes',async()=>{const f=await render();expect(f.nativeElement.querySelectorAll('[data-square]').length).toBe(64);expect(f.nativeElement.textContent).toContain("Jouer contre l'ordinateur");expect(f.nativeElement.querySelector('[data-square="e2"]').getAttribute('aria-label')).toContain('pion blanc');});
 it('annonce simulation et zones non connectées',async()=>{const f=await render();expect(f.nativeElement.textContent).toContain('SYNTHÉTIQUE');expect(f.nativeElement.textContent).toContain('non connecté');});
 it('sélectionne sans inventer de coup',async()=>{const f=await render();f.nativeElement.querySelector('[data-square="e2"]').click();f.detectChanges();expect(f.componentInstance.g.selected).toBe('e2');expect(f.componentInstance.g.state?.history).toEqual([]);});
});
