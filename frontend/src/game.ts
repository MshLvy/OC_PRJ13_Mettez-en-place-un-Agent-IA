export type Mode='study'|'computer';
export type Color='white'|'black';
export interface Ply {uci:string;san:string;fen_after:string}
export interface State {history:string[];revision:number;snapshot:string;fen:string;turn:Color;legal_moves:string[];played:Ply[];terminal:boolean;result:string|null;termination:string|null}
export interface Reply {status:'ok'|'unavailable'|'terminal'|'opening_complete';state:State;applied:Ply[];choice:{source:string;source_mode:string;reason:string;synthetic:boolean};errors:string[]}
export type Api=(path:string,body:unknown)=>Promise<unknown>;
export const api:Api=async(path,body)=>{
  const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),25000);
  try {const response=await fetch('/api/v1/game/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:abort.signal});
    const data=await response.json();if(!response.ok)throw new Error(data?.detail?.code||'Erreur du serveur');return data;
  } finally {clearTimeout(timer);}
};
export function checked(value:unknown):State {
  const s=value as State;
  if(!s||!Array.isArray(s.history)||s.history.length>256||s.revision!==s.history.length||
      !/^[a-f0-9]{64}$/.test(s.snapshot)||typeof s.fen!=='string'||s.fen.split(' ').length!==6||
      !['white','black'].includes(s.turn)||!Array.isArray(s.played)||s.played.length!==s.revision||
      !Array.isArray(s.legal_moves)||typeof s.terminal!=='boolean'||
      s.history.some((u,i)=>!/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(u)||s.played[i]?.uci!==u)||
      (s.played.length>0&&s.played.at(-1)?.fen_after!==s.fen))throw new Error('Réponse de partie incohérente');
  return s;
}
export class Game {
  mode:Mode='study';color:Color='white';source='synthetic_fixture';state?:State;
  warnings:string[]=[];busy=false;error='';status='ok';provenance='Aucun coup automatique';selected='';promotion='q';private epoch=0;
  constructor(private request:Api=api,private changed:()=>void=()=>{},private accepted:(state:State)=>void=()=>{},private invalidated:()=>void=()=>{}){}
  cancel(){this.epoch++;this.busy=false;this.selected='';this.invalidated();this.changed();}
  get computerTurn(){return !!this.state&&this.mode==='computer'&&this.state.turn!==this.color&&!this.state.terminal;}
  get canMove(){return !!this.state&&!this.busy&&!this.state.terminal&&this.status!=='opening_complete'&&!this.computerTurn;}
  get canUndo(){return !!this.state&&this.state.revision>(this.mode==='computer'&&this.color==='black'?1:0);}
  async restore(history:string[]){this.mode='study';await this.load([...history]);}
  async reset(){await this.load([]);if(this.computerTurn&&!this.busy&&!this.error)await this.play();}
  async configure(mode:Mode,color:Color){const history=mode==='study'&&this.state?[...this.state.history]:[];this.mode=mode;this.color=color;if(mode==='study')await this.load(history);else await this.reset();}
  private async load(history:string[]){
    this.invalidated();const ticket=++this.epoch;this.busy=true;this.error='';this.warnings=[];this.selected='';this.changed();
    try {const data=checked(await this.request('state',{history}));if(ticket!==this.epoch)return;
      this.state=data;this.status=data.terminal?'terminal':'ok';this.provenance='Aucun coup automatique';if(!this.computerTurn)this.accepted(data);
    }catch {if(ticket===this.epoch)this.error='État indisponible. Recommencez ; aucune réponse tardive ne sera appliquée.';}
    finally {if(ticket===this.epoch){this.busy=false;this.changed();}}
  }
  async undo(){if(!this.canUndo)return;const count=this.mode==='computer'&&this.state!.turn===this.color?2:1;await this.load(this.state!.history.slice(0,Math.max(this.color==='black'&&this.mode==='computer'?1:0,this.state!.revision-count)));}
  async play(move?:string){
    if(this.busy||!this.state||this.state.terminal||this.status==='opening_complete')return;
    if(move&&!this.canMove)return;if(!move&&!this.computerTurn)return;
    const old=this.state,ticket=++this.epoch;this.busy=true;this.error='';this.warnings=[];this.selected='';this.changed();
    try {const raw=await this.request('turn',{mode:this.mode,human_color:this.color,source:this.source,
        history:old.history,revision:old.revision,snapshot:old.snapshot,move:move??null}) as Reply;
      if(ticket!==this.epoch)return;
      const next=checked(raw.state);const delta=next.revision-old.revision;
      if(delta<0||delta>(this.mode==='study'?1:move?2:1)||old.history.some((u,i)=>next.history[i]!==u)||
         (move&&next.history[old.revision]!==move)||!['ok','unavailable','terminal','opening_complete'].includes(raw.status))throw new Error('Réponse périmée');
      if(!raw.choice||typeof raw.choice.synthetic!=='boolean'||typeof raw.choice.source!=='string'||(this.source==='theory_then_engine'&&raw.choice.synthetic))throw new Error('Provenance absente');
      this.state=next;this.status=raw.status;this.warnings=(raw.errors??[]).filter(e=>/^[A-Z0-9_]{1,80}$/.test(e)).slice(0,8);
      this.provenance=raw.choice.synthetic?'Adversaire SYNTHÉTIQUE — aucune consultation réelle':raw.choice.source==='stockfish'?'Stockfish local':raw.choice.source==='lichess_opening_explorer'?'Lichess Masters réel : coup le plus joué, pas forcément le meilleur':'Aucun coup automatique';
      this.accepted(next);
      if(raw.status==='unavailable')this.error=(raw.errors??[]).filter(e=>/^[A-Z0-9_]{1,80}$/.test(e)).join(', ')+' — '+'Adversaire indisponible. Le coup humain validé est conservé ; réessayer explicitement ou passer en étude.';
    } catch(error) {if(ticket===this.epoch)this.error='Réponse perdue, refusée ou invalide. Aucun coup local ajouté. '+(error instanceof Error&&/^[A-Z0-9_]{1,80}$/.test(error.message)?error.message:'Vous pouvez réessayer sans double coup.');}
    finally {if(ticket===this.epoch){this.busy=false;this.changed();}}
  }
  pieces(){
    const map:Record<string,string>={};const ranks=(this.state?.fen??'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1').split(' ')[0].split('/');
    ranks.forEach((row,r)=>{let file=0;for(const c of row){if(/[1-8]/.test(c))file+=Number(c);else map[String.fromCharCode(97+file++)+(8-r)]=c;}});return map;
  }
  squares(){const normal=Array.from({length:64},(_,i)=>String.fromCharCode(97+i%8)+(8-Math.floor(i/8)));return this.mode==='computer'&&this.color==='black'?normal.reverse():normal;}
  square(s:string){
    if(!this.canMove)return;
    const piece=this.pieces()[s];const own=piece&&((piece===piece.toUpperCase())===(this.state!.turn==='white'));
    if(own){this.selected=s;this.changed();return;}
    if(!this.selected)return;
    const pawn=this.pieces()[this.selected]?.toLowerCase()==='p';const move=this.selected+s+(pawn&&/[18]$/.test(s)?this.promotion:'');
    if(!this.state!.legal_moves.includes(move)){this.error='Coup interdit dans la position validée.';this.selected='';this.changed();return;}
    void this.play(move);
  }
}
