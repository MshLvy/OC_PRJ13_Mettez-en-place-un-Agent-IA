import {Api,Game,State} from './game';
import {AnalysisApi,AnalysisError,AnalysisPanel} from './analysis';
export type DemoMode='simulation'|'live';
export interface Capabilities {demo_enabled:boolean;allowed_modes:DemoMode[];default_mode:'simulation';live_reasons:string[];explorer:string;engine:string}
export class Demo {
 private disposed=false;private capabilitiesAbort?:AbortController;
 mode:DemoMode='simulation';capabilities?:Capabilities;ready=false;pending?:DemoMode;error='';testProfile=false;
 constructor(private changed:()=>void=()=>{}){}
 get active(){return !this.disposed;}
 dispose(){this.disposed=true;this.capabilitiesAbort?.abort();this.abort();}
 async load(){
  this.capabilitiesAbort=new AbortController();const timer=setTimeout(()=>this.capabilitiesAbort?.abort(),5000);
  try {const r=await fetch('/api/v1/demo/capabilities',{signal:this.capabilitiesAbort.signal});if(this.disposed)return;if(!r.ok)throw Error();const c=await r.json();
   if(typeof c.demo_enabled!=='boolean'||!Array.isArray(c.allowed_modes)||c.allowed_modes.some((v:string)=>!['simulation','live'].includes(v))||c.default_mode!=='simulation'||!Array.isArray(c.live_reasons))throw Error();
   this.capabilities=c;this.testProfile=r.headers.get('X-Demo-Test')==='offline-wiring';
  }catch{if(!this.disposed)this.error='Capacités de démonstration indisponibles : mode hors ligne verrouillé.';}finally{clearTimeout(timer);}
  if(this.disposed)return;this.ready=true;this.changed();
 }
 get enabled(){return this.ready&&this.capabilities?.demo_enabled===true;}
 get liveAllowed(){return this.enabled&&this.capabilities!.allowed_modes.includes('live');}
 propose(mode:DemoMode){if(mode===this.mode||!this.enabled||(mode==='live'&&!this.liveAllowed))return;this.pending=mode;this.changed();}
 cancel(){this.pending=undefined;this.changed();}
 async confirm(game:Game,analysis:AnalysisPanel){
  const next=this.pending;if(!next||!this.enabled||(next==='live'&&!this.liveAllowed))return;
  this.pending=undefined;
  // Aucun appel sur l'ancienne position avec les nouvelles sources.
  analysis.invalidate();game.cancel();game.state=undefined;game.error='';game.warnings=[];game.provenance='Aucun coup automatique';game.status='ok';this.mode=next;this.apply(game,analysis);this.changed();await game.reset();
 }
 apply(game:Game,analysis:AnalysisPanel){
  if(!this.enabled)return;
  game.source=this.mode==='simulation'?'synthetic_fixture':'theory_then_engine';
  analysis.policy={explorer:this.mode==='simulation'?'synthetic_fixture':'live',engine:true,engineSource:this.mode==='simulation'?'synthetic_fixture':'local_engine'};
 }
 gameApi(legacy:Api):Api{return async(path,body)=>{
  if(!this.enabled||path==='state')return legacy(path,body);
  const {source,...rest}=body as Record<string,unknown>;const mode=this.mode;
  const controller=this.gameController(),signal=controller.signal,timer=setTimeout(()=>controller.abort(),25000);try {const response=await fetch('/api/v1/demo/turn',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...rest,demo_mode:mode}),signal});
  const data=await response.json();if(!response.ok)throw new Error(data?.detail?.code||'DEMO_UNAVAILABLE');
  if(data.demo_mode!==mode||data.simulation!==(mode==='simulation')||!data.data?.choice||
     (mode==='live'&&data.data.choice.synthetic))throw new Error('DEMO_PROVENANCE_MISMATCH');
  return data.data;
  }finally{clearTimeout(timer);}
 };}
 private controller?:AbortController;
 private gameController(){this.controller?.abort();this.controller=new AbortController();return this.controller;}
 abort(){this.controller?.abort();}
 analysisApi(legacy:AnalysisApi,state:()=>State|undefined):AnalysisApi{return async(body,signal)=>{
  if(!this.enabled)return legacy(body,signal);
  const p=state(),mode=this.mode;if(!p||p.fen!==body.fen)throw new Error('DEMO_POSITION_MISMATCH');
  const r=await fetch('/api/v1/demo/analysis',{method:'POST',headers:{'Content-Type':'application/json'},signal,body:JSON.stringify({demo_mode:mode,fen:p.fen,history:p.history,revision:p.revision,snapshot:p.snapshot})});
  if(!r.ok){let code='DEMO_UNAVAILABLE';try{const v=await r.json();if(/^[A-Z0-9_]{1,80}$/.test(v?.detail?.code))code=v.detail.code;}catch{}throw new AnalysisError(r.status,code);}
  const data=await r.json();if(data.demo_mode!==mode||data.simulation!==(mode==='simulation'))throw new Error('DEMO_MODE_MISMATCH');
  return {data:data.data,simulation:data.simulation};
 };}
}
