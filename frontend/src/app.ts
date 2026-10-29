import {Component,ChangeDetectorRef,inject} from '@angular/core';
import {CommonModule} from '@angular/common';
import {FormsModule} from '@angular/forms';
import {Game,Mode,Color,api} from './game';
import {VideoPanel,VIDEO_OPENINGS,videoUrl} from './videos';
import {SessionsPanel} from './sessions';
import {ConversationPanel,safeSource} from './conversation';
import {Demo,DemoMode} from './demo';
import {OpeningPanel,openingStatus,plyLabel} from './openings';
import {AnalysisPanel,analysisApi,percent,scoreText,modeLabel,toolLabel} from './analysis';
const SYMBOLS:Record<string,string>={K:'♔',Q:'♕',R:'♖',B:'♗',N:'♘',P:'♙',k:'♚',q:'♛',r:'♜',b:'♝',n:'♞',p:'♟'};
const NAMES:Record<string,string>={k:'roi',q:'dame',r:'tour',b:'fou',n:'cavalier',p:'pion'};
@Component({selector:'app-root',standalone:true,imports:[CommonModule,FormsModule],template:`
<header><div class="brand"><span class="eyebrow">PROJET 13 · DÉMONSTRATION LOCALE</span><h1>Atelier des ouvertures</h1><p>Jouez, explorez et prenez le temps de comprendre.</p></div><div class="demo-control" *ngIf="d.enabled"><span>Sources de la démonstration</span><div role="group" aria-label="Simulation ou Réel"><button type="button" [attr.aria-pressed]="d.mode==='simulation'" (click)="d.propose('simulation')">Simulation</button><button type="button" [attr.aria-pressed]="d.mode==='live'" [disabled]="!d.liveAllowed" (click)="d.propose('live')">Réel</button></div><p *ngIf="!d.liveAllowed" class="muted">Réel non autorisé : {{d.capabilities?.live_reasons?.join(', ')}}</p><p *ngIf="d.mode==='live'">Disponibilités indépendantes, sans appel au démarrage : Lichess {{capabilityLabel(d.capabilities?.explorer)}} · Stockfish {{capabilityLabel(d.capabilities?.engine)}}. Une source absente est signalée, sans bloquer les autres.</p></div>
<p *ngIf="d.error" role="alert">{{d.error}}</p><p *ngIf="d.testProfile" class="notice">TEST DE CÂBLAGE HORS LIGNE — même « Réel » utilise ici des doubles de test, aucun fournisseur ni moteur authentique.</p>
<section *ngIf="d.pending" role="dialog" aria-modal="true" aria-label="Confirmer le nouveau départ" class="confirm"><p>Passer en {{d.pending==='live'?'Réel':'Simulation'}} ? Une nouvelle partie commencera ; coups et analyses précédents seront effacés.</p><button type="button" (click)="switchConfirmed()">Confirmer et recommencer</button><button type="button" (click)="d.cancel()">Garder la partie</button></section></header>
<main [attr.inert]="d.pending||restoringSession?'':null"><section class="play-panel" aria-label="Partie d'échecs">
 <div class="controls"><label>Votre activité<select aria-label="Mode de jeu" [ngModel]="g.mode" (ngModelChange)="configure($event,g.color)"><option value="study">Étudier une ouverture</option><option value="computer">Jouer contre l'ordinateur</option></select></label>
 <label *ngIf="g.mode==='computer'">Votre camp<select aria-label="Votre camp" [ngModel]="g.color" (ngModelChange)="configure(g.mode,$event)"><option value="white">Blancs</option><option value="black">Noirs</option></select></label></div>

 <p aria-live="polite">{{g.busy?'Validation en cours…':g.state?.terminal?'Partie terminée : '+g.state?.result:g.status==='opening_complete'?'Démonstration d’ouverture terminée (24 demi-coups). Passez en étude.':'Trait aux '+(g.state?.turn==='white'?'Blancs':'Noirs')}}</p>
 <div class="board" role="group" aria-label="Échiquier : sélectionnez une pièce puis sa destination avec Tab et Entrée">
 <button *ngFor="let s of g.squares()" type="button" [attr.data-square]="s" [attr.aria-label]="description(s)" [attr.aria-pressed]="g.selected===s" [disabled]="!g.canMove" [class.dark]="dark(s)" [class.selected]="g.selected===s" (click)="g.square(s)"><span aria-hidden="true">{{symbol(s)}}</span><small>{{s}}</small></button></div>
 <div class="actions"><button type="button" (click)="g.undo()" [disabled]="!g.canUndo">Annuler</button><button type="button" (click)="g.reset()">Recommencer</button>
 <label>Promotion<select aria-label="Pièce de promotion" [(ngModel)]="g.promotion"><option value="q">Dame</option><option value="r">Tour</option><option value="b">Fou</option><option value="n">Cavalier</option></select></label></div>
 <button *ngIf="g.computerTurn&&!g.busy&&g.status!=='opening_complete'" type="button" (click)="g.play()">Réessayer le coup ordinateur</button>
 <p *ngIf="g.warnings.length" role="status" class="muted">Choix adverse — diagnostics : {{g.warnings.join(', ')}}</p><p *ngIf="g.error" role="alert" class="error">{{g.error}}</p><p class="provenance" aria-live="polite">{{g.provenance}}</p>
 <details><summary>FEN validée par le serveur</summary><code>{{g.state?.fen}}</code></details>
</section><aside class="workspace"><section class="opening-panel" tabindex="0" aria-label="Ouverture actuelle" [attr.data-position-fen]="o.data?.position_fen" [attr.data-snapshot]="o.data?.snapshot"><h2>Ouverture actuelle</h2>
 <p class="notice" *ngIf="!d.enabled">Mode hérité hors ligne : coups SYNTHÉTIQUES légaux, pas des consultations réelles ; activez le profil de démonstration pour le sélecteur et les fixtures couvertes.</p><p class="notice" *ngIf="d.enabled&&d.mode==='simulation'">Mode <strong>SIMULATION — données fictives SYNTHÉTIQUES</strong> · positions et coups de fixture couverts uniquement. Aucune consultation Lichess. Analyse Stockfish locale possible seulement sur demande explicite ci-dessous.</p><p class="notice" *ngIf="d.mode==='live'">Mode <strong>RÉEL</strong> · Lichess Masters et Stockfish local selon leur disponibilité. Coups adverses : théorie autorisée puis moteur autorisé. Aucun repli synthétique.</p>
<p *ngIf="o.busy" role="status">Reconnaissance locale en cours…</p><p *ngIf="o.error" role="alert" class="error">{{o.error}}</p><button *ngIf="o.error&&!o.busy" type="button" (click)="o.retry()">Réessayer l’identification locale</button>
<ng-container *ngIf="o.data as opening"><p class="opening-status" aria-live="polite">{{opening.last_matched_ply&&!opening.is_current_match?'Dernière identification connue':openingStatus(opening.status)}}</p>
<h3 *ngIf="opening.display_family" class="opening-family">{{opening.display_family}} <span *ngIf="opening.eco" class="eco">{{opening.eco}}</span></h3>
<p *ngIf="opening.variation" class="opening-variation">{{opening.variation}}</p><p *ngIf="opening.status==='family_only'">Variante non encore déterminée.</p>
<p *ngIf="opening.status==='unknown'">Aucune position nommée reconnue dans cet historique ; aucun code ECO attribué.</p>
<p *ngIf="opening.status==='catalog_unavailable'">Fichiers locaux absents ou invalides. Le jeu reste disponible ; aucune consultation réseau de remplacement.</p>
<p *ngIf="opening.last_matched_ply&&!opening.is_current_match" class="opening-previous">Dernière ouverture identifiée au coup {{plyLabel(opening.last_matched_ply)}}. Hors ligne référencée depuis le demi-coup {{opening.off_line_since_ply}} ; la variante actuelle n’est pas certifiée.</p>
<ng-container *ngIf="opening.status==='ambiguous'"><p>Aucune variante choisie arbitrairement.</p><ul><li *ngFor="let c of opening.possible_candidates">{{c.eco}} · {{c.full_name}}</li></ul><p *ngIf="opening.candidates_truncated">{{opening.possible_candidates.length}} candidats affichés sur {{opening.candidate_count}}.</p></ng-container>
<p *ngIf="opening.language==='en'" class="muted">Nom anglais d’origine ; traduction éditoriale indisponible.</p><p *ngIf="opening.language==='mixed'" class="muted">Famille traduite ; variante anglaise d’origine.</p>
<p *ngIf="opening.reference" class="muted">Source factuelle locale : Lichess chess-openings · CC0. Indépendante de Simulation / Réel.</p>
<details *ngIf="opening.reference as ref"><summary>Référence et couverture</summary><p>{{ref.rows}} lignes / {{ref.positions}} positions à cette révision ; couverture limitée aux positions nommées, pas à toutes les parties possibles.</p><p>Version : {{ref.revision}}</p><p *ngIf="opening.full_name">Nom original : {{opening.full_name}}</p><p>Traductions de six familles, revue éditoriale humaine encore ouverte.</p></details></ng-container>
</section><section class="history-panel" aria-label="Historique de la partie" tabindex="0"><h2>Votre partie</h2><p *ngIf="!g.state?.played?.length">Sélectionnez une pièce pour commencer.</p><ol class="history"><li *ngFor="let ply of g.state?.played">{{ply.san}} <small>{{ply.uci}}</small></li></ol></section>
<section class="analysis-panel" tabindex="0" aria-label="Analyse de la position actuelle"><h2>Analyse de la position actuelle</h2>
<p class="muted">Les sources suivent le mode global. Aucun réglage individuel. Hors démo, les outils restent non demandés.</p>
<p *ngIf="a.elapsedMs!==null" class="muted">Durée de la dernière réponse : {{a.elapsedMs}} ms (cache possible, sans mesure de performance garantie).</p><p *ngIf="a.busy" role="status">Analyse en cours… Vous pouvez continuer à jouer.</p><p *ngIf="a.error" role="alert" class="error">{{a.error}}</p>
<button *ngIf="(a.error||a.data?.errors?.length)&&!a.busy" (click)="a.retry()" type="button">Réessayer l’analyse explicitement</button>
<p *ngIf="a.simulation" class="notice">SIMULATION DE TEST / DÉMONSTRATION : données fictives, aucun Stockfish ni fournisseur réel exécuté.</p>
<p *ngIf="a.data" class="analysis-status" aria-live="polite">État global : {{a.data.status}}</p>
<h3>Théorie Lichess</h3><p class="explorer-status">{{toolLabel(a.data?.tools?.explorer?.status)}}</p>
<p *ngIf="a.errorFor('explorer')" class="error">{{a.errorFor('explorer')}}</p>
<ng-container *ngIf="a.data?.tools?.explorer?.result as result"><p>{{result.source_mode==='live'?'Lichess Masters réel':modeLabel(result.source_mode)}} · base {{result.base}}</p>
<p>Fréquences observées ou simulées : les coups les plus joués ne sont pas nécessairement les meilleurs.</p>
<div class="table-wrap" tabindex="0"><table><caption>Coups candidats de la position affichée</caption><thead><tr><th>Coup</th><th>Parties</th><th>Blancs / nulles / Noirs</th><th>Victoires blanches</th></tr></thead><tbody><tr *ngFor="let m of result.moves"><td>{{m.san}} <small>{{m.uci}}</small></td><td>{{m.statistics?.games??'—'}}</td><td>{{m.statistics?m.statistics.white+' / '+m.statistics.draws+' / '+m.statistics.black:'Statistiques absentes'}}</td><td>{{percent(m.statistics,'white')}}</td></tr></tbody></table></div></ng-container>
<h3>Évaluation Stockfish</h3><p class="engine-status">{{toolLabel(a.data?.tools?.engine?.status)}}</p><p *ngIf="a.errorFor('engine')" class="error">{{a.errorFor('engine')}}</p>
<ng-container *ngIf="a.data?.tools?.engine?.result as result"><p>{{a.simulation?'SIMULATION — DONNÉES FICTIVES':modeLabel(result.source_mode)}}</p><p class="engine-score">{{scoreText(result)}}</p>
<p>Profondeur {{result.depth??'non fournie'}} / limite {{result.limits.depth}}, temps {{result.limits.time_seconds}} s, {{result.limits.threads}} thread, hash {{result.limits.hash_mb}} Mo.</p><p>{{a.simulation?'Version de fixture':'Version'}} : {{result.engine_version??'non fournie'}}</p><p *ngIf="result.best_move_uci">{{a.simulation?'Coup de fixture':'Coup calculé'}} : {{result.best_move_san}} ({{result.best_move_uci}})</p><p class="muted">Un score moteur est une évaluation bornée, jamais une probabilité de gagner.</p></ng-container>
<section class="local-engine-panel" *ngIf="d.mode==='simulation'"><h3>Stockfish local à la demande</h3><p>Analyse locale indépendante des coups et statistiques fictifs. Aucun appel fournisseur externe.</p>
<button type="button" (click)="analyzeLocal()" [disabled]="!g.state||g.busy||localEngine.busy||d.capabilities?.engine!=='binary_present_not_probed'">Analyser avec Stockfish local</button>
<p *ngIf="d.capabilities?.engine!=='binary_present_not_probed'" class="muted">Stockfish non activé ou binaire absent ; le reste de la démonstration reste disponible.</p>
<p *ngIf="localEngine.busy" role="status">Analyse locale demandée en cours…</p><p *ngIf="localEngine.error" role="alert">{{localEngine.error}}</p><p *ngIf="localEngine.errorFor('engine')" role="alert">{{localEngine.errorFor('engine')}}</p>
<ng-container *ngIf="localEngine.data?.tools?.engine?.result as local"><p class="local-engine-score">{{scoreText(local)}}</p><p>{{d.testProfile?'TEST DE CÂBLAGE — runner moteur simulé':'Source : Stockfish local · local_engine · aucune fixture'}} · {{local.engine_version}}</p></ng-container></section>
<details *ngIf="a.data"><summary>Provenance de l’analyse</summary><ul><li *ngFor="let p of a.data.provenance">{{p.tool}} : {{p.source}} · {{modeLabel(p.source_mode)}} · tentative {{p.attempted?'oui':'non'}}</li></ul><code>{{a.fen}}</code></details>
</section><section class="conversation-panel" tabindex="0" aria-label="Conseiller pédagogique"><h2>Conseiller pédagogique</h2>
<p>Extraits V3 réels du corpus local — même en Simulation. Simulation : Qwen local ou restitution déterministe. Réel : Mistral API à la soumission explicite par défaut, ou Groq selon la configuration backend ; les essais payants nécessitent le GO opérateur distinct. BGE/Milvus est optionnel, non connecté sans activation du worker ; le mode réellement utilisé et les indisponibilités sont affichés pour chaque demande.</p>
<p class="muted">Pour essayer : en mode Étudier, jouez e2–e4 puis c7–c5 et posez la question proposée.</p>
<label>Intention pédagogique<select aria-label="Intention pédagogique" [ngModel]="c.intent" (ngModelChange)="c.setIntent($event)"><option value="position">Conseiller ma position actuelle</option><option value="opening_theory">Comprendre une ouverture</option></select></label>
<p *ngIf="c.intent==='opening_theory'" class="notice">Théorie générale : les extraits ne portent pas sur la position affichée. Précisez une seule ouverture.</p>
<label>Votre question<textarea aria-label="Question au conseiller" maxlength="600" [(ngModel)]="c.question" rows="3"></textarea></label>
<button type="button" (click)="c.ask(d.mode)" [disabled]="!c.position||c.busy||g.busy||!c.question.trim()">Chercher des sources et demander un conseil</button>
<p *ngIf="c.busy" role="status">Recherche documentaire en cours…</p><p *ngIf="c.error" role="alert">{{c.error}}</p>
<ng-container *ngIf="c.data as result"><p class="conversation-status" aria-live="polite">{{result.message}}</p>
<p>État : {{result.status}} · génération : {{result.generation.status}} · recherche : {{result.retrieval_mode}} · dense : {{result.dense_status}}</p>
<p *ngIf="result.retrieval_trace as trace">BGE : {{trace.dense_reason}} · {{trace.elapsed_ms}} ms · {{trace.collection}}</p>
<p *ngIf="result.timings as t" class="muted">Total backend : {{t['total_ms']??'n/d'}} ms · Retrieval : {{t['retrieval_ms']??'n/d'}} ms</p>
<p *ngIf="result.generation.timings as t" class="muted">Prompt : {{t['prompt_ms']??'n/d'}} ms · Découverte : {{t['discovery_ms']??'n/d'}} ms · Génération HTTP : {{t['inference_http_ms']??'n/d'}} ms · Validation : {{t['validation_ms']??'n/d'}} ms · Serveur préremplissage : {{t['server_prompt_ms']??'n/d'}} ms · Serveur génération : {{t['server_generation_ms']??'n/d'}} ms</p>
<p class="generation-provenance">Générateur : {{result.generation.provider||'none'}} · {{result.generation.engine}} · demandé : {{result.generation.requested_model||result.generation.model}} · renvoyé : {{result.generation.actual_model||'non fourni'}} · {{result.generation.duration_ms||0}} ms</p>
<p *ngIf="result.generation.reason" class="muted">{{result.generation.reason}} · {{result.generation.error_code}} · {{result.generation.validation_code}}</p>
<p *ngIf="result.generation.usage as usage">Tokens : entrée {{usage.prompt_tokens}} · sortie {{usage.completion_tokens}} · total {{usage.total_tokens}} (usage renvoyé, coût non calculé)</p>
<p *ngIf="result.generation.status==='deterministic'" class="notice">RESTITUTION DOCUMENTAIRE DÉTERMINISTE — aucun LLM n’a rédigé de réponse.</p>
<p *ngIf="result.generation.status==='test_double'" class="notice">GÉNÉRATION DE TEST — aucun LLM local ni API réellement consulté.</p>
<ng-container *ngIf="result.generation.answer as answer"><p *ngFor="let paragraph of answer.paragraphs">{{paragraph.text}} <small>{{paragraph.citation_ids.join(', ')}}</small></p><p *ngIf="answer.moves_uci?.length">Suite UCI vérifiée, non jouée automatiquement : {{answer.moves_uci?.join(' ')}}</p></ng-container>
<article *ngFor="let p of result.passages" class="conversation-source"><h3>Extrait documentaire · {{p.family}}</h3><p class="source-text">{{p.text}}</p>
<p>Portée : {{p.scope==='opening_theory'?'théorie d’ouverture, hors position affichée':'position de référence courante'}} · revue humaine en attente · {{p.license}}</p>
<ul><li *ngFor="let source of p.source_citations"><a *ngIf="safeSource(source.url) as url" [href]="url" target="_blank" rel="noopener noreferrer">{{source.work}} · {{source.id}} · révision {{source.revid}}</a><p>{{source.attribution}}</p></li></ul>
<details><summary>Attribution, modification et preuve</summary><p>{{p.attribution}}</p><p>{{p.modification_notice}}</p><p>{{p.corpus_version}} · {{p.chunk_id}}</p><code>{{p.text_sha256}}</code></details></article>
<p *ngFor="let limit of result.limits" class="muted">{{limit}}</p></ng-container>
<details *ngIf="c.position"><summary>Position de cette demande</summary><code>{{c.position.fen}}</code></details>
</section><section class="sessions-panel" tabindex="0" aria-label="Séances pédagogiques"><h2>Mes séances locales</h2>
<p>Aucune sauvegarde automatique. Ce bouton conserve l’ouverture choisie, FEN/historique, dates et, si coché, la réponse affichée munie d’un reçu du serveur. Pas de passages complets, vidéos, prompts ou clés. Ne saisissez pas de données personnelles.</p>
<label>Ouverture de la séance<select aria-label="Ouverture de la séance" [ngModel]="s.opening" (ngModelChange)="s.setOpening($event)"><option value="">Choisir explicitement</option><option *ngFor="let item of videoOpenings" [value]="item[0]">{{item[1]}}</option></select></label>
<label><input type="checkbox" [(ngModel)]="s.includeAnswer" [disabled]="!c.data?.session_receipt"> Inclure la réponse validée affichée et ses IDs de citations (revue humaine en attente)</label>
<button type="button" (click)="s.save(c.data?.session_receipt)" [disabled]="s.busy||!s.position||!s.opening||g.busy">Sauvegarder la séance</button>
<button type="button" (click)="s.list()" [disabled]="s.busy">Afficher les séances</button><button *ngIf="s.next" type="button" (click)="s.list(s.next)" [disabled]="s.busy">Séances suivantes</button>
<p role="status">{{s.message}}</p><p *ngIf="s.busy">Persistance en cours…</p>
<ul><li *ngFor="let row of s.items">{{row.opening}} · {{row.created_at}} <button type="button" (click)="s.consult(row.id)" [disabled]="s.busy">Consulter</button> <button type="button" (click)="resumeSession(row.id)" [disabled]="s.busy||g.busy">Reprendre en Étudier / Simulation</button> <button type="button" (click)="s.remove(row.id)" [disabled]="s.busy">Supprimer</button></li></ul>
<article *ngIf="s.loaded as saved"><h3>Séance archivée : {{saved.opening}}</h3><p>{{saved.id}} · {{saved.history.length}} demi-coups · {{saved.created_at}}</p><code>{{saved.fen}}</code><div *ngFor="let exchange of saved.exchanges"><p>{{exchange.question}}</p><p *ngFor="let paragraph of exchange.answer.paragraphs">{{paragraph.text}} <small>{{paragraph.citation_ids.join(', ')}}</small></p><p>{{exchange.provider}} · {{exchange.model}} · {{exchange.retrieval_mode}} · contrôles applicatifs, pas de validation humaine experte · CC-BY-SA4.0</p></div></article>
<p class="muted">Une reprise revalide les coups côté serveur, sans appel moteur, vidéo ou LLM. Les archives ne sont pas de nouvelles recommandations.</p></section>
<section class="videos-panel" tabindex="0" aria-label="Vidéos pédagogiques"><h2>Vidéos</h2>
<p>Complément pédagogique non certifié : ni preuve FEN exacte, ni citation du RAG, ni contenu visionné. Revue humaine non effectuée.</p>
<p class="muted">La source vidéo dépend du serveur, indépendamment de Simulation / Réel. Ce clic peut consulter YouTube si le serveur l’autorise.</p>
<label>Ouverture choisie<select aria-label="Ouverture des vidéos" [ngModel]="v.opening" (ngModelChange)="v.setOpening($event)"><option value="">Choisir explicitement une ouverture</option><option *ngFor="let item of videoOpenings" [value]="item[0]">{{item[1]}}</option></select></label>
<label>Thème à approfondir<select aria-label="Thème vidéo" [ngModel]="v.topic" (ngModelChange)="v.setTopic($event)"><option value="">Règle de développement si admissible</option><option value="develop_minor_pieces">Développement des pièces mineures</option><option value="king_safety">Sécurité du roi</option><option value="central_control">Contrôle du centre</option></select></label>
<button type="button" (click)="exploreVideos()" [disabled]="!v.canAsk||g.busy">Explorer les vidéos</button>
<p *ngIf="v.busy" role="status">Recherche vidéo en cours…</p><p *ngIf="v.error" role="alert">{{v.error}}</p>
<p *ngIf="v.position&&v.position.history.length>24" class="muted">Historique hors contrat vidéo : aucune reconstitution ou troncature pour justifier position/conseil.</p>
<ng-container *ngIf="v.data as result"><p aria-live="polite">{{result.status}} · {{result.video_count}} vidéo(s) · {{result.test_transport?'TRANSPORT DE TEST — aucun appel YouTube réel':result.source_mode==='live'?'Source : API YouTube réelle':result.source_mode==='synthetic_fixture'?'SIMULATION — métadonnées fictives, aucun lien réel':'YouTube désactivé'}} · recherches tentées : {{result.attempted_searches}}</p>
<article *ngFor="let row of result.intentions"><h3>{{videoIntent(row.intent)}}</h3><p>{{row.status}} · {{row.reason}}</p><p>{{row.why_this_video}}</p><ng-container *ngIf="row.video as video"><a *ngIf="!result.synthetic&&!result.test_transport&&videoUrl(video) as url; else videoText" [href]="url" target="_blank" rel="noopener noreferrer">{{video.title}}</a><ng-template #videoText><p>{{video.title}}</p></ng-template><p>{{video.channel}} <span *ngIf="video.published_at">· {{video.published_at}}</span></p></ng-container></article></ng-container>
<p class="muted">Aucune vidéo, miniature, iframe ou transcription chargée automatiquement.</p></section></aside></main>`})
export class App {
  private cd=inject(ChangeDetectorRef);
  capabilityLabel(value:string|undefined){return ({authorized_not_probed:'autorisé, réseau non testé',configuration_unavailable:'configuration indisponible',binary_present_not_probed:'binaire présent, analyse non lancée',binary_missing:'binaire absent',disabled:'désactivé'} as Record<string,string>)[value??'']??'non déterminé';}
  localEngine=new AnalysisPanel(analysisApi,()=>this.cd.markForCheck());
  analyzeLocal(){if(this.d.mode!=='simulation'||this.g.busy||!this.g.state||this.d.capabilities?.engine!=='binary_present_not_probed')return;this.localEngine.policy={explorer:'disabled',engine:true,engineSource:'local_engine'};void this.localEngine.accept(this.g.state);}
  restoringSession=false;
  s=new SessionsPanel(undefined,()=>this.cd.markForCheck());
  async resumeSession(ident:string){
    if(this.g.busy||this.restoringSession)return;
    const saved=await this.s.consult(ident);if(!saved||this.g.busy||this.d.pending)return;
    this.restoringSession=true;this.d.mode='simulation';this.d.cancel();this.d.apply(this.g,this.a);this.g.cancel();
    try{await this.g.restore(saved.history);if(!this.g.error&&this.g.state?.fen===saved.fen){this.s.loaded=saved;this.s.opening=saved.opening;this.s.message='Séance reprise en Étudier / Simulation, sans consultation externe.';}else this.s.message='Reprise refusée : position incohérente.';}
    finally{this.restoringSession=false;this.cd.markForCheck();}
  }
  v=new VideoPanel(undefined,()=>this.cd.markForCheck());
  exploreVideos(){if(!this.g.busy)void this.v.explore();}
  videoOpenings=VIDEO_OPENINGS;videoUrl=videoUrl;
  videoIntent(intent:string){return ({understand_opening:'Comprendre l’ouverture',understand_position:'Comprendre la position',deepen_advice:'Approfondir un conseil'} as Record<string,string>)[intent]??intent;}
  c=new ConversationPanel(undefined,()=>this.cd.markForCheck());
  safeSource=safeSource;
  d=new Demo(()=>this.cd.markForCheck());
  o=new OpeningPanel(undefined,()=>this.cd.markForCheck());
  a=new AnalysisPanel(this.d.analysisApi(analysisApi,()=>this.g.state),()=>this.cd.markForCheck());
  g=new Game(this.d.gameApi(api),()=>this.cd.markForCheck(),s=>{if(this.restoringSession)this.a.invalidate();else void this.a.accept(s);void this.o.accept(s);this.c.accept(s);this.v.accept(s);this.s.accept(s);this.localEngine.invalidate();},()=>{this.d.abort();this.a.invalidate();this.o.invalidate();this.c.invalidate();this.v.invalidate();this.s.invalidate();this.localEngine.invalidate();});
  percent=percent;scoreText=scoreText;modeLabel=modeLabel;toolLabel=toolLabel;openingStatus=openingStatus;plyLabel=plyLabel;
  ngOnDestroy(){this.d.dispose();this.g.cancel();this.a.dispose();this.o.dispose();this.c.dispose();this.v.dispose();this.s.dispose();this.localEngine.dispose();}
  async ngOnInit(){await this.d.load();if(!this.d.active)return;this.d.apply(this.g,this.a);void this.g.reset();}
  switchConfirmed(){void this.d.confirm(this.g,this.a);}
  configure(mode:Mode,color:Color){void this.g.configure(mode,color);}
  symbol(s:string){return SYMBOLS[this.g.pieces()[s]]??'';}
  description(s:string){const p=this.g.pieces()[s];return s+' : '+(p?NAMES[p.toLowerCase()]+' '+(p===p.toUpperCase()?'blanc':'noir'):'case vide');}
  dark(s:string){return (s.charCodeAt(0)+Number(s[1]))%2===0;}
}
