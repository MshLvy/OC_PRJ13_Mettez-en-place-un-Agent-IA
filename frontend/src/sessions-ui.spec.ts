/** Angular DOM and HTTP doubles only. */
import '@angular/compiler';
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
import {state} from './videos-fixtures';
import {savedSession} from './sessions-fixtures';
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
it('no automatic session request; explicit save and archived text safely rendered',async()=>{
 const fetch=vi.fn(async(url:string)=>({ok:true,json:async()=>url==='/api/v1/sessions'?savedSession():state}));vi.stubGlobal('fetch',fetch);TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();f.detectChanges();expect(fetch.mock.calls.filter(c=>c[0].includes('/sessions'))).toHaveLength(0);
 const panel=f.nativeElement.querySelector('.sessions-panel');expect(panel.textContent).toContain('Aucune sauvegarde automatique');expect(panel.querySelector('input').checked).toBe(false);const select=panel.querySelector('select');select.value='sicilienne';select.dispatchEvent(new Event('change'));await f.whenStable();f.detectChanges();panel.querySelector('button').click();await f.whenStable();f.detectChanges();expect(fetch.mock.calls.filter(c=>c[0].includes('/sessions'))).toHaveLength(1);expect(panel.textContent).toContain('Séance sauvegardée');
});
it('resume revalidates history with game endpoint and does not call analysis, providers, video or conversation',async()=>{
 const calls:string[]=[];vi.stubGlobal('fetch',vi.fn(async(url:string)=>{calls.push(url);return {ok:true,json:async()=>url.startsWith('/api/v1/sessions/')?savedSession():state};}));TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();await vi.waitFor(()=>expect(f.componentInstance.g.state).toBeDefined());await vi.waitFor(()=>expect(f.componentInstance.g.busy).toBe(false));await vi.waitFor(()=>expect(f.componentInstance.a.busy).toBe(false));calls.length=0;
 await f.componentInstance.resumeSession('c'.repeat(32));await f.whenStable();f.detectChanges();expect(calls).toContain('/api/v1/game/state');expect(calls.filter(url=>/analysis|conversation|videos|turn/.test(url))).toEqual([]);expect(f.componentInstance.g.mode).toBe('study');expect(f.componentInstance.d.mode).toBe('simulation');expect(f.componentInstance.s.loaded?.id).toBe('c'.repeat(32));
});
