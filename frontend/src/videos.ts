import {State} from './game';
export const VIDEO_OPENINGS=[['espagnole','Espagnole'],['italienne','Italienne'],['sicilienne','Sicilienne'],['francaise','Française'],['caro_kann','Caro-Kann'],['gambit_dame','Gambit dame']] as const;
export type VideoOpening=typeof VIDEO_OPENINGS[number][0];
export type Topic=''|'develop_minor_pieces'|'king_safety'|'central_control';
export interface Video {video_id:string;title:string;channel:string;url:string|null;thumbnail_url:string|null;published_at:string|null}
export interface VideoOutcome {intent:'understand_opening'|'understand_position'|'deepen_advice';status:'ok'|'skipped'|'empty'|'disabled'|'unavailable';reason:string;why_this_video:string;query:string|null;video:Video|null;evidence:{history_verified:boolean;opening_prefix_verified:boolean;opening_origin:'user_selected';advice_provenance:'user_selected'|'rule_based'|null;side_to_move:'white'|'black';rule:string|null}}
export interface Exploration {status:'ok'|'partial'|'empty'|'disabled'|'unavailable';source:'youtube_data_api';source_mode:'disabled'|'synthetic_fixture'|'live';synthetic:boolean;test_transport?:boolean;editorial_review:'not_reviewed';fen_normalized:string;intentions:VideoOutcome[];video_count:number;attempted_searches:number;steps:string[]}
export interface VideoRequest {action:'explore_videos';opening:VideoOpening;fen:string;history?:string[];language:'fr';advice_topic?:Exclude<Topic,''>}
export type VideoApi=(body:VideoRequest,signal:AbortSignal)=>Promise<unknown>;
export const videoApi:VideoApi=async(body,signal)=>{
 const response=await fetch('/api/v1/videos/explore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});
 if(!response.ok)throw new Error('VIDEO_UNAVAILABLE');return response.json();
};
const plain=(v:unknown,max:number)=>typeof v==='string'&&v.length<=max&&!/[<>\p{Cc}\p{Cf}\p{Cs}]/u.test(v);
export function videoUrl(video:Video){return /^[A-Za-z0-9_-]{11}$/.test(video.video_id)&&video.url==='https://www.youtube.com/watch?v='+video.video_id?video.url:null;}
export function validateVideos(value:unknown,position:State):Exploration {
 const r=value as Exploration;
 if(!r||!['ok','partial','empty','disabled','unavailable'].includes(r.status)||r.source!=='youtube_data_api'||!['disabled','synthetic_fixture','live'].includes(r.source_mode)||r.synthetic!==(r.source_mode!=='live')||r.test_transport!==undefined&&typeof r.test_transport!=='boolean'||r.editorial_review!=='not_reviewed'||r.fen_normalized!==position.fen||!Array.isArray(r.intentions)||r.intentions.length!==3||!Number.isInteger(r.video_count)||r.video_count<0||r.video_count>3||!Number.isInteger(r.attempted_searches)||r.attempted_searches<0||r.attempted_searches>3)throw new Error('INVALID_VIDEO_RESPONSE');
 const ids=new Set<string>();const intents=['understand_opening','understand_position','deepen_advice'];
 for(const [i,row] of r.intentions.entries()){
  if(row.intent!==intents[i]||!['ok','skipped','empty','disabled','unavailable'].includes(row.status)||! /^[A-Z0-9_]{1,80}$/.test(row.reason)||!plain(row.why_this_video,600)||row.query!==null&&!plain(row.query,240)||!row.evidence||row.evidence.opening_origin!=='user_selected'||typeof row.evidence.history_verified!=='boolean'||typeof row.evidence.opening_prefix_verified!=='boolean')throw new Error('INVALID_VIDEO_RESPONSE');
  const v=row.video;if(!v){if(row.status==='ok')throw new Error('MISSING_VIDEO');continue;}
  if(row.status!=='ok'||! /^[A-Za-z0-9_-]{11}$/.test(v.video_id)||ids.has(v.video_id)||!plain(v.title,240)||!v.title.trim()||!plain(v.channel,200)||!v.channel.trim())throw new Error('INVALID_VIDEO');ids.add(v.video_id);
  if(r.synthetic?(v.url!==null||v.thumbnail_url!==null):!videoUrl(v))throw new Error('INVALID_VIDEO_URL');
  if(v.thumbnail_url!==null&&v.thumbnail_url!==undefined&&!new RegExp('^https://i\\.ytimg\\.com/vi/'+v.video_id+'/(default|mqdefault|hqdefault)\\.jpg$').test(v.thumbnail_url))throw new Error('INVALID_VIDEO_URL');
  if(v.published_at!==null&&v.published_at!==undefined&&(!plain(v.published_at,40)||!Number.isFinite(Date.parse(v.published_at))))throw new Error('INVALID_VIDEO_DATE');
 }
 if(ids.size!==r.video_count)throw new Error('INVALID_VIDEO_COUNT');return r;
}
export class VideoPanel {
 opening:VideoOpening|''='';topic:Topic='';position?:State;data?:Exploration;busy=false;error='';
 private ticket=0;private abort?:AbortController;private disposed=false;
 constructor(private request:VideoApi=videoApi,private changed:()=>void=()=>{},private timeout=22000){}
 private cancel(){this.ticket++;this.abort?.abort();this.busy=false;this.data=undefined;this.error='';}
 invalidate(){this.cancel();this.position=undefined;if(!this.disposed)this.changed();}
 accept(position:State){this.cancel();this.position={...position,history:[...position.history]};this.changed();}
 setOpening(value:VideoOpening|''){this.cancel();this.opening=value;this.changed();}
 setTopic(value:Topic){this.cancel();this.topic=value;this.changed();}
 dispose(){this.disposed=true;this.invalidate();}
 get canAsk(){return !this.disposed&&!this.busy&&!!this.position&&!!this.opening;}
 async explore(){
  if(!this.canAsk)return;const position=this.position!,id=++this.ticket;this.abort=new AbortController();const abort=this.abort;
  const body:VideoRequest={action:'explore_videos',opening:this.opening as VideoOpening,fen:position.fen,language:'fr'};
  if(position.history.length<=24)body.history=[...position.history];
  if(this.topic)body.advice_topic=this.topic;
  this.busy=true;this.data=undefined;this.error='';this.changed();const timer=setTimeout(()=>abort.abort(),this.timeout);
  try{const result=await this.request(body,abort.signal);if(this.disposed||id!==this.ticket)return;if(abort.signal.aborted)throw new Error('TIMEOUT');this.data=validateVideos(result,position);}
  catch{if(!this.disposed&&id===this.ticket)this.error=abort.signal.aborted?'Délai vidéo dépassé ; aucune nouvelle tentative automatique.':'Vidéos indisponibles ou réponse incohérente ; aucun lien ajouté.';}
  finally{clearTimeout(timer);if(!this.disposed&&id===this.ticket){this.busy=false;this.changed();}}
 }
}
