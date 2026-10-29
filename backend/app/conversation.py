"""I09 vertical: common admitted retrieval, explicit mode-selected generation."""
from typing import Literal
import hashlib,re,unicodedata,time
import chess
from pydantic import BaseModel,ConfigDict,Field,StrictBool,field_validator
from app.game import HistoryRequest,rebuild,snapshot,GameError
from app.positions import diagnose_fen,FenValidationError
from app import conversation_data as data
from app.conversation_mistral import MistralAdapter,Generation
from app.conversation_retrieval import Retrieval
from app.conversation_generators import GeneratorRouter

class ConversationRequest(HistoryRequest):
    history:list[str]|None=Field(default=None,max_length=256)
    fen:str=Field(strict=True,min_length=1,max_length=256)
    snapshot:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    question:str=Field(strict=True,min_length=1,max_length=600)
    request_generation:StrictBool=False
    demo_mode:Literal['simulation','live']='simulation'
    intent:Literal['position','opening_theory']='position'
    @field_validator('history')
    @classmethod
    def bounded_uci(cls,values):
        return None if values is None else super().bounded_uci(values)
    @field_validator('question')
    @classmethod
    def visible(cls,q):
        q=q.strip()
        if not q or any(unicodedata.category(c) in ('Cc','Cf','Cs') for c in q):raise ValueError('INVALID_QUESTION')
        return q
class Source(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str;url:str;revid:int;work:str;attribution:str;license:str;license_url:str;authors_history_url:str;fragment_sha256:str
class Evidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    chunk_id:str;passage_id:str;family:str;text:str;text_sha256:str
    corpus_version:Literal['pilot-fr-v3-enriched-0.1']=data.VERSION
    license:Literal['CC-BY-SA-4.0']='CC-BY-SA-4.0'
    attribution:str;modification_notice:str;source_citations:list[Source]
    reference_fen:str
    scope:Literal['current_reference_position','opening_theory']='current_reference_position'
    human_review:Literal['pending']='pending'
    production_approved:Literal[False]=False
class ConversationResponse(BaseModel):
    session_receipt:str|None=Field(default=None,max_length=32768)
    status:Literal['invalid','abstain','unavailable','partial','answered']
    reason:str;message:str
    fen:str|None=None;snapshot:str|None=None
    passages:list[Evidence]=Field(default_factory=list,max_length=3)
    generation:Generation=Field(default_factory=lambda:Generation(status='generation_disabled'))
    retrieval_mode:Literal['offline_bm25_v3','hybrid_bm25_bge_v3','bm25_fallback_v3']='offline_bm25_v3'
    intent:Literal['position','opening_theory']='position'
    retrieval_trace:dict=Field(default_factory=dict)
    dense_status:Literal['integration_pending','ready','unavailable']='integration_pending'
    calibrated_threshold:None=None
    timings:dict[str,float|None]=Field(default_factory=dict)
    limits:list[str]=Field(default_factory=lambda:['Le mode de recherche et la provenance dense sont déclarés pour chaque demande ; aucun seuil de confiance validé.','Corpus expérimental ; revue humaine en attente. Une correspondance de position ne prouve pas un conseil stratégique.'])

def evidence_from_row(row, intent):
    """Shared serialization only; ranking/admission algorithms stay unchanged."""
    return Evidence(chunk_id=row['chunk_id'], passage_id=row['passage_id'], family=row['family'],
        text=row['text'], text_sha256=row['text_sha256'], attribution=row['attribution'],
        modification_notice=row['modification_notice'], source_citations=row['source_citations'],
        reference_fen=row['fen'], scope='opening_theory' if intent=='opening_theory' else 'current_reference_position')

MESSAGES={'INVALID_CONTEXT':'FEN ou historique invalide. Aucun outil documentaire ou génératif appelé.','POSITION_MISMATCH':'La position, l’historique ou son instantané ne concordent pas. Relancez depuis la position courante.','OUTSIDE_SCOPE':'Cette demande dépasse les documents d’ouvertures disponibles. Aucun score moteur, statistique actuelle, achat vidéo ou table de finales ne sera inventé.','UNSAFE_INSTRUCTIONS':'Les instructions demandant de contourner les sources ne sont pas traitées.','CLARIFY_OPENING':'Précisez une ouverture et jouez sa position de référence avant de chercher.','POSITION_SCOPE_MISMATCH':'Les références de cette ouverture ne correspondent pas à la position actuelle. Aucun conseil transféré entre variantes.','INSUFFICIENT_EVIDENCE':'Aucun extrait admissible ne répond suffisamment à cette demande dans la position affichée. Précisez votre question.','V3_UNAVAILABLE':'Le corpus V3 local est indisponible ou son intégrité n’est pas vérifiée.','GENERATION_DISABLED':'Extraits documentaires disponibles ci-dessous. Génération Mistral désactivée : aucun conseil rédigé par un LLM.','EVIDENCE_ONLY':'Extraits documentaires uniquement, sans recommandation générée.','PROVIDER_UNAVAILABLE':'Générateur indisponible ; seuls les extraits vérifiés sont présentés.','GENERATION_REJECTED':'La sortie générée est écartée : abstention du modèle ou contrôles de citations, de scope ou de légalité non satisfaits.','TEST_GENERATION':'GÉNÉRATION DE TEST — transport injecté, aucune inférence locale ou consultation Mistral réelle.','SOURCED_GENERATION':'Réponse générée à partir des extraits admis, avec citations contrôlées. Revue pédagogique humaine en attente.','LOCAL_GENERATOR_UNAVAILABLE':'Restitution documentaire déterministe : générateur local indisponible. Les extraits ci-dessous ne sont pas une réponse LLM.'}

def outside_scope(question):
    q=data.normalize(question)
    return bool(re.search(r'\b(finale|finales|table de mat|tablebase|abonnement|acheter|achat|statistique|statistiques|hier|stockfish|score chiffre|evaluation chiffree|meilleur coup)\b|taux de victoire|taux de gain',q))

class ConversationService:
    def __init__(self,generator=None,retrieval=None):
        self.generator=generator if generator is not None else GeneratorRouter();self.retrieval=retrieval or Retrieval()
    def ask(self,body):
        request_start=time.monotonic()
        context={'intent':body.intent}
        def reply(status,reason,passages=None,generation=None):
            measured={'total_ms':round((time.monotonic()-request_start)*1000,2),'retrieval_ms':context.get('retrieval_trace',{}).get('elapsed_ms'),'generation_ms':generation.duration_ms if generation else None}
            return ConversationResponse(status=status,reason=reason,message=MESSAGES[reason],passages=passages or [],generation=generation or Generation(status='generation_disabled'),timings=measured,**context)
        try:
            fen=diagnose_fen(body.fen).fen_normalized
            if body.history is not None:
                board,_=rebuild(body.history)
                if board.fen(en_passant='fen')!=fen or body.snapshot is not None and snapshot(body.history)!=body.snapshot:return reply('invalid','POSITION_MISMATCH')
                identity=snapshot(body.history)
            else:
                if body.snapshot is not None:return reply('invalid','POSITION_MISMATCH')
                identity=hashlib.sha256(fen.encode()).hexdigest()
            context.update(fen=fen,snapshot=identity)
        except (GameError,FenValidationError,ValueError):return reply('invalid','INVALID_CONTEXT')
        if data.injection(body.question):return reply('abstain','UNSAFE_INSTRUCTIONS')
        if outside_scope(body.question):return reply('abstain','OUTSIDE_SCOPE')
        try:
            rows,reason,trace=self.retrieval.retrieve(body.question,fen,body.intent)
            context.update(retrieval_mode=trace['method'],dense_status=trace['dense_status'],retrieval_trace=trace)
            if reason:return reply('abstain',reason)
            passages=[evidence_from_row(r,body.intent) for r in rows if not data.injection(r['text'])]
            if not passages:return reply('abstain','INSUFFICIENT_EVIDENCE')
        except (OSError,ValueError,KeyError,TypeError):return reply('unavailable','V3_UNAVAILABLE')
        if not body.request_generation:return reply('partial','EVIDENCE_ONLY',passages)
        if body.intent=='opening_theory' and not isinstance(self.generator,GeneratorRouter):
            result=reply('partial','EVIDENCE_ONLY',passages);result.message='Théorie d’ouverture : ces extraits ne constituent pas un conseil sur la position affichée. Génération désactivée.';return result
        generation=self.generator.generate_context(body,fen,passages) if isinstance(self.generator,GeneratorRouter) else self.generator.generate(body.question,fen,passages)
        reason={'generation_disabled':'GENERATION_DISABLED','provider_unavailable':'PROVIDER_UNAVAILABLE','abstain':'GENERATION_REJECTED','test_double':'TEST_GENERATION','generated':'SOURCED_GENERATION','deterministic':'LOCAL_GENERATOR_UNAVAILABLE'}[generation.status]
        return reply('answered' if generation.status in ('test_double','generated') else 'abstain' if generation.status=='abstain' else 'partial',reason,passages,generation)
