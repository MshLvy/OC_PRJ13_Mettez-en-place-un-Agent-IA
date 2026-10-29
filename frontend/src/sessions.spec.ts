/** Storage/API doubles only; no Mongo persistence claim. */
import {it,expect,vi} from 'vitest';
import {SessionsPanel} from './sessions';
import {state} from './videos-fixtures';
import {savedSession} from './sessions-fixtures';
it('never saves/lists on accept or opening choice; explicit save sends closed snapshot and receipt only on opt-in',async()=>{
 const api=vi.fn(async(..._args:any[])=>savedSession());const p=new SessionsPanel(api);p.accept(state);p.setOpening('sicilienne');expect(api).not.toHaveBeenCalled();await p.save('TOKEN');expect(api).toHaveBeenCalledTimes(1);expect(api.mock.calls[0][2]).toEqual({opening:'sicilienne',history:[],fen:state.fen,snapshot:state.snapshot,receipts:[]});p.includeAnswer=true;await p.save('TOKEN');expect(api.mock.calls[1][2].receipts).toEqual(['TOKEN']);expect(p.message).toContain('sauvegardée');
});
it('listing and deletion are explicit, no silent refetch or retry',async()=>{
 const row=savedSession();const api=vi.fn(async(method:string)=>method==='GET'?{items:[row],next_cursor:null}:{status:'deleted',id:row.id});const p=new SessionsPanel(api);await p.list();expect(p.items).toHaveLength(1);await p.remove(row.id);expect(p.items).toHaveLength(0);expect(api).toHaveBeenCalledTimes(2);
});
it.each(['SESSIONS_DISABLED','PRIVATE_PASSWORD_TIMEOUT'])('failure %s never claims success or reflects private error',async message=>{
 const api=vi.fn(async()=>{throw new Error(message);});const p=new SessionsPanel(api);p.accept(state);p.setOpening('sicilienne');await p.save();expect(p.loaded).toBeUndefined();expect(p.message).not.toContain('sauvegardée');expect(p.message).not.toContain('PRIVATE');expect(api).toHaveBeenCalledTimes(1);
});
it('double save is blocked and late response after position change ignored',async()=>{
 let resolve!:(v:unknown)=>void;const api=vi.fn(()=>new Promise(r=>resolve=r));const p=new SessionsPanel(api);p.accept(state);p.setOpening('sicilienne');const a=p.save();await p.save();p.accept({...state,snapshot:'b'.repeat(64)});resolve(savedSession());await a;expect(api).toHaveBeenCalledTimes(1);expect(p.loaded).toBeUndefined();
});
it('save response with mismatched snapshot rejected',async()=>{
 const p=new SessionsPanel(async()=>({...savedSession(),snapshot:'b'.repeat(64)}));p.accept(state);p.setOpening('sicilienne');await p.save();expect(p.loaded).toBeUndefined();expect(p.message).toContain('non confirmé');
});
it('consult is explicit and returned identity must match',async()=>{
 const api=vi.fn(async()=>savedSession());const p=new SessionsPanel(api);expect(await p.consult('d'.repeat(32))).toBeUndefined();expect(api).toHaveBeenCalledTimes(1);expect(await p.consult('c'.repeat(32))).toBeDefined();
});
it('changing opening invalidates a pending save response',async()=>{
 let resolve!:(v:unknown)=>void;const p=new SessionsPanel(()=>new Promise(r=>resolve=r));p.accept(state);p.setOpening('sicilienne');const pending=p.save();p.setOpening('francaise');resolve(savedSession());await pending;expect(p.loaded).toBeUndefined();expect(p.opening).toBe('francaise');
});
