/** Angular DOM only, all requests mocked. No physical/API proof. */
import '@angular/compiler';
import {afterEach,beforeAll,it,expect,vi} from 'vitest';
import {provideZonelessChangeDetection} from '@angular/core';
import {TestBed} from '@angular/core/testing';
import {BrowserTestingModule,platformBrowserTesting} from '@angular/platform-browser/testing';
import {App} from './app';
import {state,videoReply} from './videos-fixtures';
beforeAll(()=>TestBed.initTestEnvironment(BrowserTestingModule,platformBrowserTesting()));
afterEach(()=>{TestBed.resetTestingModule();vi.unstubAllGlobals();});
it.each([false,true])('one video button, no autocall, safe rendering; live protocol=%s (double)',async live=>{
 const fetch=vi.fn(async(url:string)=>({ok:true,json:async()=>url.includes('/videos/explore')?videoReply(live):state}));vi.stubGlobal('fetch',fetch);
 TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();f.detectChanges();
 const panel=f.nativeElement.querySelector('.videos-panel');expect(panel.querySelectorAll('button')).toHaveLength(1);expect(panel.querySelector('button').disabled).toBe(true);expect(fetch.mock.calls.filter(x=>x[0].includes('/videos'))).toHaveLength(0);
 const select=panel.querySelector('select[aria-label="Ouverture des vidéos"]');select.value='sicilienne';select.dispatchEvent(new Event('change'));await f.whenStable();f.detectChanges();
 expect(fetch.mock.calls.filter(x=>x[0].includes('/videos'))).toHaveLength(0);panel.querySelector('button').click();await f.whenStable();f.detectChanges();
 expect(fetch.mock.calls.filter(x=>x[0].includes('/videos/explore'))).toHaveLength(1);expect(panel.textContent).toContain('OPENING_PREFIX_NOT_ESTABLISHED');expect(panel.textContent).toContain('Revue humaine non effectuée');expect(panel.querySelectorAll('iframe,img,script')).toHaveLength(0);
 if(live){const link=panel.querySelector('a');expect(link.href).toBe('https://www.youtube.com/watch?v=FIXTURE0001');expect(link.rel).toBe('noopener noreferrer');}else{expect(panel.querySelector('a')).toBeNull();expect(panel.textContent).toContain('SIMULATION');}
 f.componentInstance.g.cancel();f.detectChanges();expect(panel.querySelector('article')).toBeNull();
});
it('live test transport never exposes a pretend real video link',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>state})));TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();const data=videoReply(true);data.test_transport=true;f.componentInstance.v.data=data;f.changeDetectorRef.markForCheck();f.detectChanges();const panel=f.nativeElement.querySelector('.videos-panel');expect(panel.textContent).toContain('TRANSPORT DE TEST');expect(panel.querySelector('a')).toBeNull();
});

it.each(['disabled','empty','unavailable'] as const)('displays %s without inventing a video',async status=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>state})));TestBed.configureTestingModule({imports:[App],providers:[provideZonelessChangeDetection()]});const f=TestBed.createComponent(App);f.detectChanges();await f.whenStable();const data=videoReply(false);data.status=status;data.video_count=0;data.source_mode=status==='disabled'?'disabled':'synthetic_fixture';for(const row of data.intentions){row.video=null;row.status=status;row.reason=status==='disabled'?'YOUTUBE_DISABLED':status==='empty'?'NO_ACCEPTABLE_CANDIDATES':'YOUTUBE_TIMEOUT';}f.componentInstance.v.data=data;f.changeDetectorRef.markForCheck();f.detectChanges();const panel=f.nativeElement.querySelector('.videos-panel');expect(panel.textContent).toContain(status);expect(panel.querySelector('a')).toBeNull();expect(panel.textContent).not.toContain('EXEMPLE DE TEST');
});
