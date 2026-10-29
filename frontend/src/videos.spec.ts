/** Entire suite uses protocol doubles. No genuine YouTube response or API. */
import {it,expect,vi,afterEach} from 'vitest';
import {VideoPanel,Exploration,validateVideos} from './videos';
import {State} from './game';
import {state,videoReply} from './videos-fixtures';
afterEach(()=>vi.useRealTimers());
it('explicit opening required; no request on accept/settings; one click one POST and no raw advice',async()=>{
 let resolve!:(v:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new VideoPanel(api);p.accept(state);expect(p.canAsk).toBe(false);p.setOpening('sicilienne');p.setTopic('king_safety');expect(api).not.toHaveBeenCalled();const a=p.explore();await p.explore();expect(api).toHaveBeenCalledTimes(1);expect(api.mock.calls[0]).toBeDefined();resolve(videoReply());await a;expect(p.data?.video_count).toBe(1);
});
it('sends exact validated history without inferring an opening or forwarding LLM answer',async()=>{
 const api=vi.fn(async(..._args:any[])=>videoReply());const p=new VideoPanel(api);p.accept(state);p.setOpening('sicilienne');await p.explore();expect(api.mock.calls[0][0]).toEqual({action:'explore_videos',opening:'sicilienne',fen:state.fen,history:[],language:'fr'});
});
it('never truncates or fabricates a too-long history',async()=>{
 const api=vi.fn(async(..._args:any[])=>videoReply());const p=new VideoPanel(api);p.accept({...state,history:Array(25).fill('a2a3')});p.setOpening('sicilienne');await p.explore();expect(api.mock.calls[0][0]).not.toHaveProperty('history');
});
it.each(['position','opening','topic','dispose'] as const)('ignores late response after %s changes',async(change)=>{
 let resolve!:(v:unknown)=>void;const p=new VideoPanel(()=>new Promise(r=>resolve=r));p.accept(state);p.setOpening('sicilienne');const pending=p.explore();if(change==='position')p.accept({...state,snapshot:'b'.repeat(64)});if(change==='opening')p.setOpening('francaise');if(change==='topic')p.setTopic('king_safety');if(change==='dispose')p.dispose();resolve(videoReply());await pending;expect(p.data).toBeUndefined();
});
it('timeout exposes no fake link and never retries',async()=>{
 vi.useFakeTimers();let resolve!:(v:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new VideoPanel(api,undefined,10);p.accept(state);p.setOpening('sicilienne');const pending=p.explore();await vi.advanceTimersByTimeAsync(11);resolve(videoReply());await pending;expect(p.error).toContain('Délai');expect(api).toHaveBeenCalledTimes(1);
});
it.each(['fen','url','xss','duplicate','synthetic_link','count'] as const)('rejects malformed or unsafe %s',kind=>{
 const r=videoReply(true);if(kind==='fen')r.fen_normalized='different';if(kind==='url')r.intentions[0].video!.url='https://evil.example';if(kind==='xss')r.intentions[0].video!.title='<script>BAD</script>';if(kind==='duplicate'){r.intentions[1]={...r.intentions[0],intent:'understand_position'};r.video_count=2;}if(kind==='synthetic_link'){r.synthetic=true;r.source_mode='synthetic_fixture';}if(kind==='count')r.video_count=3;expect(()=>validateVideos(r,state)).toThrow();
});
