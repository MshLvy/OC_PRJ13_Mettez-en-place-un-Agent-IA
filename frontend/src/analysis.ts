import {State} from './game';
export type ExplorerMode='disabled'|'synthetic_fixture'|'live';
export interface Policy {explorer:ExplorerMode;engine:boolean;engineSource?:'synthetic_fixture'|'local_engine'}
export interface Counts {white:number;draws:number;black:number;games:number}
export interface MoveStats {uci:string;san:string;statistics:Counts|null}
export interface ExplorerResult {fen_normalized:string;source:string;source_mode:string;base:string;position_statistics:Counts|null;moves:MoveStats[]}
export interface Evaluation {fen_normalized:string;source:string;source_mode:string;engine_version:string|null;depth:number|null;best_move_uci:string|null;best_move_san:string|null;score:{type:'cp'|'mate';value:number;perspective:'white';bound:'none'|'lower'|'upper'}|null;limits:{time_seconds:number;depth:number;threads:number;hash_mb:number;analysis_applied:boolean}}
export type ToolStatus='not_requested'|'skipped_terminal'|'ok'|'empty'|'disabled'|'error'|'skipped_theory_available';
export interface Outcome<T> {requested:boolean;status:ToolStatus;http_status?:number;result:T|null}
export interface Analysis {status:'ok'|'partial'|'terminal';fen_normalized:string;position:{fen_normalized:string};tools:{explorer:Outcome<ExplorerResult>;engine:Outcome<Evaluation>};errors:{tool:string;code:string;http_status:number;retry_after_seconds?:number|null}[];provenance:{tool:string;source:string;source_mode:string;attempted:boolean}[]}
export interface Envelope {data:unknown;simulation:boolean}
export type AnalysisApi=(body:{fen:string;explorer_mode:ExplorerMode;include_engine:boolean},signal:AbortSignal)=>Promise<Envelope>;
export class AnalysisError extends Error {constructor(public status:number,public code:string){super(code);}}
export const analysisApi:AnalysisApi=async(body,signal)=>{
  const response=await fetch('/api/v1/analysis/orchestrate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
  if(!response.ok){let code='ANALYSIS_UNAVAILABLE';try{const value=await response.json();if(/^[A-Z0-9_]{1,80}$/.test(value?.detail?.code))code=value.detail.code;}catch{}throw new AnalysisError(response.status,code);}
  return {data:await response.json(),simulation:response.headers.get('X-Analysis-Simulation')==='j06_i02_offline'};
};
const statuses=['not_requested','skipped_terminal','ok','empty','disabled','error','skipped_theory_available'];
function require(value:unknown,message:string):asserts value {if(!value)throw new Error(message);}
function counts(value:Counts|null){if(value===null)return;require(value&&['white','draws','black','games'].every(k=>Number.isSafeInteger(value[k as keyof Counts])&&value[k as keyof Counts]>=0),'Statistiques invalides');require(value.games===value.white+value.draws+value.black,'Comptes incohérents');}
export function validateAnalysis(value:unknown,fen:string,policy:Policy):Analysis {
 const data=value as Analysis;
 require(data&&['ok','partial','terminal'].includes(data.status)&&data.fen_normalized===fen&&data.position?.fen_normalized===fen,'FEN ou état incohérent');
 require(data.tools&&Array.isArray(data.errors)&&Array.isArray(data.provenance),'Contrat analyse invalide');
 for(const [name,wanted] of [['explorer',policy.explorer!=='disabled'],['engine',policy.engine]] as const){
  const outcome=data.tools[name];require(outcome&&outcome.requested===wanted&&statuses.includes(outcome.status),'Préférences incohérentes');
  if(!wanted)require(outcome.status==='not_requested'&&outcome.result==null,'Outil activé implicitement');
  if(['not_requested','skipped_terminal','disabled','error','skipped_theory_available'].includes(outcome.status))require(outcome.result==null,'Résultat sur outil indisponible');
  if(outcome.result)require(outcome.result.fen_normalized===fen,'FEN outil incohérente');
 }
 const explorer=data.tools.explorer;
 if(['ok','empty'].includes(explorer.status)){
  const r=explorer.result;require(r&&r.source==='lichess_opening_explorer'&&r.base==='masters'&&r.source_mode===policy.explorer&&Array.isArray(r.moves)&&r.moves.length<=12,'Provenance Explorer incohérente');counts(r.position_statistics);require((explorer.status==='empty')===(r.moves.length===0)&&new Set(r.moves.map(m=>m.uci)).size===r.moves.length,'Liste de coups incohérente');
  for(const m of r.moves){require(/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(m.uci)&&typeof m.san==='string'&&m.san.length<=24,'Coup invalide');counts(m.statistics);}
 }
 const engine=data.tools.engine;
 if(engine.status==='ok'){
  const r=engine.result;require(r&&r.source==='stockfish'&&r.source_mode===(policy.engineSource??'local_engine')&&r.score&&r.limits,'Provenance moteur incohérente');
  const s=r.score;require(s.perspective==='white'&&['cp','mate'].includes(s.type)&&Number.isSafeInteger(s.value)&&['none','lower','upper'].includes(s.bound)&&(s.type!=='mate'||s.value!==0),'Score invalide');
  require(Number.isFinite(r.limits.time_seconds)&&r.limits.time_seconds>=0.05&&r.limits.time_seconds<=1&&r.limits.threads===1&&r.limits.hash_mb===16&&r.limits.depth===20,'Limites moteur incohérentes');
  require(r.depth===null||(Number.isInteger(r.depth)&&r.depth>=0&&r.depth<=20),'Profondeur invalide');
  require(r.best_move_uci===null||/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(r.best_move_uci),'Meilleur coup invalide');
 }
 return data;
}
export function percent(c:Counts|null,side:'white'|'draws'|'black'){return c&&c.games>0?(100*c[side]/c.games).toFixed(1)+' %':'—';}
export function scoreText(r:Evaluation|null){
 if(!r?.score)return 'Aucun score disponible';const s=r.score,b=s.bound==='lower'?'≥ ':s.bound==='upper'?'≤ ':'';
 return s.type==='cp'?b+(s.value>0?'+':'')+(s.value/100).toFixed(2)+' pion(s) · '+s.value+' centipions · perspective Blancs':b+(s.value>0?'Mat favorable aux Blancs en ':'Mat contre les Blancs en ')+Math.abs(s.value)+' coup(s)';
}
export function modeLabel(mode:string){return ({synthetic_fixture:'SIMULATION — fixture synthétique',disabled:'Désactivé',local_engine:'Protocole moteur local',live:'Consultation live',injected_transport:'Transport injecté — consultation réelle non démontrée',local_diagnostic:'Diagnostic local'} as Record<string,string>)[mode]??'Provenance non reconnue';}
export function toolLabel(status:ToolStatus|undefined){return ({not_requested:'Non demandé (désactivé dans l’interface)',skipped_terminal:'Non exécuté : position terminale',ok:'Disponible',empty:'Aucun coup théorique disponible',disabled:'Désactivé par le service',error:'Outil indisponible',skipped_theory_available:'Moteur non exécuté : coups théoriques disponibles'} as Record<string,string>)[status??'']??'En attente d’une position validée';}
export class AnalysisPanel {
 elapsedMs:number|null=null;policy:Policy={explorer:'disabled',engine:false};data?:Analysis;busy=false;error='';simulation=false;fen='';snapshot='';
 private position?:State;private generation=0;private abort?:AbortController;private activeKey='';private cache?:{key:string;data:Analysis;simulation:boolean};private disposed=false;
 constructor(private request:AnalysisApi=analysisApi,private changed:()=>void=()=>{},private timeout=25000){}
 private key(p:State){return p.snapshot+'|'+p.fen+'|'+this.policy.explorer+'|'+this.policy.engine+'|'+(this.policy.engineSource??'local_engine');}
 invalidate(){this.generation++;this.abort?.abort();this.abort=undefined;this.activeKey='';this.position=undefined;this.data=undefined;this.busy=false;this.error='';this.elapsedMs=null;this.fen='';this.snapshot='';if(!this.disposed)this.changed();}
 dispose(){this.disposed=true;this.invalidate();}
 configure(explorer:ExplorerMode,engine:boolean){if(!['disabled','synthetic_fixture'].includes(explorer)||typeof engine!=='boolean')return;this.policy={explorer,engine};if(this.position)void this.accept(this.position);}
 async accept(position:State){
  if(this.disposed)return;const key=this.key(position);this.position=position;
  if(key===this.activeKey)return;
  this.generation++;this.abort?.abort();const id=this.generation;this.activeKey=key;
  this.data=undefined;this.error='';this.fen=position.fen;this.snapshot=position.snapshot;
  if(this.cache?.key===key){this.data=this.cache.data;this.simulation=this.cache.simulation;this.busy=false;this.changed();return;}
  this.simulation=false;this.abort=new AbortController();const abort=this.abort;this.busy=true;this.changed();
  const started=Date.now();const timer=setTimeout(()=>abort.abort(),this.timeout);
  try {const response=await this.request({fen:position.fen,explorer_mode:this.policy.explorer,include_engine:this.policy.engine},abort.signal);
    if(id!==this.generation||this.disposed)return;if(abort.signal.aborted)throw new Error('Délai expiré');
    const result=validateAnalysis(response.data,position.fen,this.policy);
    this.data=result;this.simulation=response.simulation;this.cache={key,data:result,simulation:response.simulation};
  }catch(error){if(id!==this.generation||this.disposed)return;
    this.data=undefined;this.error=abort.signal.aborted?'Délai client dépassé ; aucun retry automatique.':error instanceof AnalysisError?
      (error.status===403?'Outil non autorisé par la configuration serveur. ':error.status===503?'Service occupé ou indisponible. ':error.status===504?'Délai serveur dépassé. ':'Analyse indisponible. ')+error.code:
      'Réponse absente ou incohérente avec la position actuelle ; analyse écartée.';
  }finally {clearTimeout(timer);if(id===this.generation&&!this.disposed){this.busy=false;this.elapsedMs=Date.now()-started;this.changed();}}
 }
 retry(){if(!this.busy&&this.position){const p=this.position;this.activeKey='';this.cache=undefined;void this.accept(p);}}
 errorFor(tool:string){return this.data?.errors.filter(e=>e.tool===tool).map(e=>/^[A-Z0-9_]{1,80}$/.test(e.code)?e.code+(Number.isSafeInteger(e.retry_after_seconds)&&e.retry_after_seconds!>0?' — attendre '+e.retry_after_seconds+' s avant de réessayer':''):'ERREUR_OUTIL').join(', ')??'';}
}
