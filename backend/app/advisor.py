"""Récupération de passages cités, pas génération conversationnelle."""
import hashlib
import math
import re
from threading import Lock
from time import monotonic
from typing import Literal
import unicodedata
import chess

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.advisor_data import load_search, legacy_modules, policy
from app.advisor_dense import DenseError, DenseRunner, DenseSettings, readiness, COLLECTION, REVISION
from app.game import HistoryRequest, GameError
from app.openings import OpeningIdentifier, OpeningResponse

_GATE = Lock()
POLICY_VERSION = 'advisor-evidence-j07-i01-v1'


class RetrieveRequest(HistoryRequest):
    question: str = Field(strict=True, min_length=1, max_length=600)
    mode: Literal['local', 'hybrid', 'dense'] = 'local'

    @field_validator('question')
    @classmethod
    def visible_question(cls, value):
        value = value.strip()
        if (not value or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value)
                or any(c in value for c in '<>`') or '://' in value):
            raise ValueError('INVALID_ADVISOR_QUESTION')
        return value


class Citation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    citation_id: str
    chunk_id: str
    doc_id: str
    title: str
    text: str
    language: Literal['fr'] = 'fr'
    license: Literal['CC0-1.0'] = 'CC0-1.0'
    source_mode: Literal['local_original_corpus'] = 'local_original_corpus'
    source_path: str
    source_url: str | None
    repository_url: str
    citation_uri: str
    author: str
    attribution: str
    version: str
    source_revision: str
    corpus_version: Literal['pilot-fr-v1'] = 'pilot-fr-v1'
    text_sha256: str
    retrieval_sha256: str
    fact_url: str
    fact_revision: str
    fact_name: str
    fact_eco: str
    fact_pgn: str
    reference_fen: str
    scope: Literal['current_position', 'reference_position_only']
    human_review: Literal['pending'] = 'pending'
    engine_validated: Literal[False] = False
    exact_routes: list[str]
    bm25_score: float
    dense_score: float | None = None
    dense_evidence_kind: Literal['not_used', 'real_milvus', 'test_double']
    fusion_score: float
    matching_terms: list[str]


class DenseEvidence(BaseModel):
    status: Literal['not_requested', 'ok', 'unavailable'] = 'not_requested'
    evidence_kind: Literal['not_used', 'real_milvus', 'test_double'] = 'not_used'
    network_probed: bool | None = False
    worker_started: bool = False
    reasons: list[str] = Field(default_factory=list)
    collection: str | None = None
    model_revision: str | None = None
    metadata_verified: bool = False


class FutureFeatures(BaseModel):
    enabled: Literal[False] = False
    memory: Literal[False] = False
    videos_opt_in: Literal[False] = False


class RetrievalResponse(BaseModel):
    status: Literal['ok', 'partial', 'abstain', 'unavailable']
    mode: Literal['local', 'hybrid', 'dense']
    question: str
    opening: OpeningResponse
    topic: str | None
    requested_openings: list[str]
    passages: list[Citation] = Field(max_length=3)
    abstention_reasons: list[str]
    warnings: list[str]
    errors: list[str]
    trace: list[str]
    duration_ms: float
    dense: DenseEvidence
    policy_version: Literal['advisor-evidence-j07-i01-v1'] = POLICY_VERSION
    top_k: Literal[3] = 3
    retries: Literal[0] = 0
    generated_answer: None = None
    generation_executed: Literal[False] = False
    conversation: FutureFeatures = Field(default_factory=FutureFeatures)


class LocalCapability(BaseModel):
    status: Literal['available', 'unavailable']
    corpus: Literal['pilot-fr-v1'] | None = None
    chunks: int | None = None
    human_review: Literal['pending'] | None = None
    reason: str | None = None


class DenseCapability(BaseModel):
    authorized: bool
    status: Literal['blocked', 'configured_not_probed']
    reasons: list[str]
    collection: str
    dimension: Literal[384]
    model_revision: str
    network_probed: Literal[False] = False


class AdvisorCapabilities(BaseModel):
    local: LocalCapability
    exact: Literal['available', 'unavailable']
    bm25: Literal['available', 'unavailable']
    dense: DenseCapability
    v2: dict
    limits: dict
    generation_executed: Literal[False] = False
    conversation_enabled: Literal[False] = False
    videos_enabled: Literal[False] = False


TOPICS = {
 'development': {'developpement','developper','developpe','developpent','pieces','cavaliers','fous'},
 'center': {'centre','central','centrales','centraux','controler','controle','chaine','c5'},
 'king_safety': {'roque','roquer','securite'},
 'opening_overview': {'principes','principe','plan','plans','idee','idees'},
}
# Périmètre documentaire volontairement étroit ; ne prétend pas détecter tout hors-domaine.
OUTSIDE = {'recette','cuisine','cuisiner','poker','bourse','medecine','football','python','javascript',
           'mat','mater','finale','finales','tablebase','integrale','youtube','video','videos','moteur','stockfish',
           'ignore','ignorer','instructions','systeme','secret','secrets','api'}
NUISANCE = {'ouverture','ouvertures','echecs','cette','ce','ces','pourquoi','comment','position','actuelle',
            'ici','variante','variantes','conseil','donne','role','debut','partie'}


def sha(value):return hashlib.sha256(value.encode()).hexdigest()


class AdvisorService:
    def __init__(self, openings=None, *, search_loader=load_search, settings=None, dense=None, clock=monotonic, gate=None):
        self.openings = openings or OpeningIdentifier()
        self.search_loader = search_loader
        self.settings = settings or DenseSettings.from_env()
        self.dense = dense or DenseRunner(self.settings)
        self.clock = clock
        self.gate = gate if gate is not None else _GATE

    def capabilities(self):
        reasons = readiness(self.settings)
        try:
            search = self.search_loader()
            local = {'status': 'available', 'corpus': 'pilot-fr-v1', 'chunks': len(search.chunks), 'human_review': 'pending'}
        except Exception:
            local = {'status': 'unavailable', 'reason': 'ADVISOR_CORPUS_UNAVAILABLE'}
        return {'local': local, 'exact': local['status'], 'bm25': local['status'],
            'dense': {'authorized': self.settings.allowed, 'status': 'blocked' if reasons else 'configured_not_probed',
                'reasons': reasons, 'collection': COLLECTION, 'dimension': 384, 'model_revision': REVISION,
                'network_probed': False},
            'v2': {'runtime_authorized': False, 'ingestion_authorized': False},
            'limits': {'top_k': 3, 'question_chars': 600, 'max_body_bytes': 16384, 'history_plies': 256, 'budget_seconds': 25,
                       'dense_worker_seconds': 20, 'worker_address_space_bytes': 4*1024**3,
                       'worker_cpu_seconds': 18, 'worker_threads': 1, 'retries': 0, 'concurrency': 1},
            'generation_executed': False, 'conversation_enabled': False, 'videos_enabled': False}

    def retrieve(self, request):
        if request.mode != 'local' and not self.settings.allowed:
            raise GameError('ADVISOR_DENSE_NOT_ALLOWED', 403)
        if not self.gate.acquire(blocking=False):raise GameError('ADVISOR_BUSY', 503)
        start = self.clock()
        try:return self._retrieve(request, start)
        finally:self.gate.release()

    def _retrieve(self, request, start):
        opening = self.openings.identify(request.history)
        trace = ['validated_history', 'opening_identified_locally']
        warnings = ['EXPERIMENTAL_PEDAGOGICAL_TEXTS_HUMAN_REVIEW_PENDING', 'RETRIEVAL_IS_NOT_A_GENERATED_ANSWER']
        errors = ['OPENING_CATALOG_UNAVAILABLE'] if opening.status=='catalog_unavailable' else [];reasons = [];topic = None;requested = []
        if opening.last_matched_ply and not opening.is_current_match:warnings.append('OPENING_CONTEXT_IS_HISTORICAL_NOT_CURRENT_CERTAINTY')
        if opening.status=='ambiguous':warnings.append('OPENING_CONTEXT_AMBIGUOUS')
        dense_info = {'status': 'not_requested', 'evidence_kind': 'not_used', 'network_probed': False}
        def reply(status, passages=None):
            return RetrievalResponse(status=status, mode=request.mode, question=request.question, opening=opening,
                topic=topic, requested_openings=requested, passages=passages or [], abstention_reasons=reasons,
                warnings=warnings, errors=errors, trace=trace, duration_ms=round((self.clock()-start)*1000, 3), dense=dense_info)
        try:search = self.search_loader();engine = legacy_modules();contract = policy()
        except Exception:
            errors.append('ADVISOR_CORPUS_UNAVAILABLE');trace.append('corpus_unavailable');return reply('unavailable')
        trace.append('verified_pilot_v1_read_only')
        normalize = engine.normalize
        q = normalize(request.question);tokens = set(engine.tokenize(request.question))
        if tokens & OUTSIDE:
            reasons.append('OUTSIDE_DOCUMENTED_SCOPE');trace.append('abstain_before_retrieval');return reply('abstain')
        aliases = {}
        for c in search.chunks:
            aliases.setdefault(c['opening_id'], set()).update(normalize(s) for s in [c['opening_name'], *c['aliases'], c['source']['facts']['name'].partition(':')[0]])
        for ident, names in aliases.items():
            if any(' '+name+' ' in ' '+q+' ' for name in names):requested.append(ident)
        codes = set(re.findall(r'\b[a-e][0-9]{2}\b', q))
        by_code = {c['opening_id'] for c in search.chunks if c['eco'].lower() in codes}
        if codes:
            requested = sorted(set(requested) | by_code)
            if not by_code:
                reasons.append('ECO_NOT_IN_CORPUS');return reply('abstain')
        if len(requested) > 1:
            reasons.append('MULTIPLE_OPENINGS_NOT_SUPPORTED');return reply('abstain')
        vocabulary = set().union(*(set(engine.tokenize(c['retrieval_text'])) for c in search.chunks))
        vocabulary |= set().union(*TOPICS.values()) | NUISANCE | {'importants','important','essentiel','essentiels','quand','quel','quelle','quels','quelles','apprendre','jouer','actuelle','apres','coups','est','cette','dans','cela'}
        vocabulary |= set(engine.tokenize((opening.family or '')+' '+(opening.variation or '')))
        if any(t not in vocabulary and not re.fullmatch(r'[a-e][0-9]{2}|[a-h][1-8](?:[a-h][1-8][qrbn]?)?',t) for t in tokens):
            reasons.append('QUESTION_TERMS_OUTSIDE_CORPUS');trace.append('closed_vocabulary_abstention');return reply('abstain')
        exact_reference = bool(re.fullmatch(r'(?:eco )?[a-e][0-9]{2}', q) or any(q in names for names in aliases.values())
                               or q in ('quelle ouverture actuelle', 'quelle est l ouverture actuelle', 'quelle est cette ouverture'))
        for name, words in TOPICS.items():
            if tokens & words:topic = name;break
        if exact_reference:topic = 'reference_lookup'
        if topic is None:
            reasons.append('QUESTION_TOPIC_NOT_SUPPORTED');return reply('abstain')
        scope_ids = set(requested)
        if not scope_ids and opening.is_current_match and opening.status in ('identified', 'family_only'):
            family = normalize(opening.family or '')
            scope_ids = {ident for ident, names in aliases.items() if family in names}
        if requested and opening.family and normalize(opening.family) not in aliases[requested[0]]:
            warnings.append('QUESTION_OPENING_DIFFERS_FROM_BOARD')
        position_specific = bool(tokens & {'ici','maintenant','position','variante','najdorf'} or 'ce coup' in q or 'cette ligne' in q)
        # « ouverture actuelle » est un lookup de référence, pas une demande de conseil.
        if exact_reference:position_specific = False
        position_key = chess.Board(opening.position_fen).epd(en_passant='legal')
        native_hits, native_route = search.exact({'kind':'uci','moves':tuple(request.history),'position_key':position_key})
        position_ids = {h['chunk_id'] for h in native_hits}
        if exact_reference and not requested and not scope_ids and not position_ids:
            reasons.append('NO_DOCUMENTED_OPENING_FOR_REFERENCE');return reply('abstain')
        if position_specific and not position_ids:
            reasons.append('NO_CURRENT_POSITION_EVIDENCE');return reply('abstain')
        if not scope_ids and opening.is_current_match and opening.family and not requested:
            reasons.append('RECOGNIZED_OPENING_OUTSIDE_CORPUS');return reply('abstain')
        exact = {h['chunk_id']:[native_route] for h in native_hits}
        # Réemploi des voies exactes J04 ; les matches alias/ECO restent bibliographiques.
        for ident in sorted(scope_ids):
            label = next(c['opening_name'] for c in search.chunks if c['opening_id']==ident)
            hits, route = search.exact(engine.prepare({'kind':'alias','value':label}))
            for h in hits:exact.setdefault(h['chunk_id'], []).append(route+'_document_scope')
        for code in sorted(codes):
            hits, route = search.exact(engine.prepare({'kind':'eco','value':code}))
            for h in hits:exact.setdefault(h['chunk_id'], []).append(route+'_document_scope')
        trace += ['exact_document_scope', 'bm25_question_only']
        scores = search.bm25.scores(tokens)
        bm25 = {c['chunk_id']:s for c,s in zip(search.chunks,scores) if s >= contract['bm25_min_score'] and s > 0}
        dense_scores = {}
        if self.clock()-start > 3:
            errors.append('ADVISOR_LOCAL_BUDGET_EXCEEDED');return reply('unavailable')
        if request.mode != 'local':
            trace.append('dense_opt_in')
            try:
                data = self.dense.search(request.question)
                for h in data['hits']:
                    if h['chunk_id'] not in search.by_id or not math.isfinite(h['score']):raise DenseError('DENSE_FOREIGN_RESULT')
                    if h['score'] >= contract['e5_min_score']:dense_scores[h['chunk_id']] = h['score']
                kind = self.dense.evidence_kind
                dense_info.update(status='ok', evidence_kind=kind, network_probed=kind=='real_milvus', worker_started=getattr(self.dense,'last_worker_started',False),
                    collection=COLLECTION, model_revision=REVISION, metadata_verified=data.get('metadata_verified', False))
                trace.append('dense_'+kind)
            except Exception as error:
                code = str(error) if isinstance(error, DenseError) and re.fullmatch('[A-Z0-9_]{1,80}', str(error)) else 'DENSE_UNAVAILABLE'
                errors.append(code);started_worker=getattr(self.dense,'last_worker_started',False);dense_info.update(status='unavailable', reasons=[code], worker_started=started_worker, network_probed=None if started_worker else False);trace.append('dense_unavailable_no_fake_fallback')
        if request.mode == 'dense':
            exact = {};bm25 = {}
            if errors:return reply('unavailable')
        # Fusion de rangs, jamais addition de scores sur des échelles incompatibles.
        rank_exact = {ident:i+1 for i,ident in enumerate(sorted(exact,key=lambda n:(n not in position_ids,n)))}
        rank_bm = {ident:i+1 for i,ident in enumerate(sorted(bm25,key=lambda n:(-bm25[n],n)))}
        rank_dense = {ident:i+1 for i,ident in enumerate(sorted(dense_scores,key=lambda n:(-dense_scores[n],n)))}
        accepted = []
        for ident in set(exact)|set(bm25)|set(dense_scores):
            c = search.by_id[ident]
            if scope_ids and c['opening_id'] not in scope_ids:continue
            if codes and c['eco'].lower() not in codes:continue
            if position_specific and ident not in position_ids:continue
            body_tokens = set(engine.tokenize(c['text']))
            matching = sorted((tokens & body_tokens) - NUISANCE - set().union(*(set(n.split()) for names in aliases.values() for n in names)))
            if not exact_reference:
                theme_words = TOPICS.get(topic, set())
                if not (body_tokens & theme_words) or not matching:continue
                if ident not in bm25 and ident not in dense_scores:continue
            elif ident not in exact and not (request.mode=='dense' and ident in dense_scores):continue
            value = sum(1/(contract['rrf_k']+r[ident]) for r in (rank_exact,rank_bm,rank_dense) if ident in r)
            accepted.append((value, ident, matching))
        accepted.sort(key=lambda row:(-row[0],row[1]))
        trace.append('rrf_deduplicate_document_top3')
        citations = [];seen = set()
        for value, ident, matching in accepted:
            c = search.by_id[ident]
            if c['doc_id'] in seen:continue
            seen.add(c['doc_id'])
            prose = c['source']['prose'];facts = c['source']['facts']
            if (sha(c['text']) != c['text_sha256'] or sha(c['retrieval_text']) != c['content_sha256']
                    or prose['content_sha256'] != c['text_sha256']):
                errors.append('ADVISOR_CITATION_INTEGRITY');return reply('unavailable')
            citations.append(Citation(citation_id='J04:'+ident, chunk_id=ident, doc_id=c['doc_id'], title=c['title'], text=c['text'],
                source_path=prose['source_path'], source_url=prose['source_url'], repository_url=contract['repository_url']+'/blob/'+contract['source_commit']+'/'+prose['source_path'], citation_uri='repo://'+prose['source_path'],
                author=prose['author'], attribution=prose['attribution'], version=prose['version'], source_revision=prose['source_revision'],
                text_sha256=c['text_sha256'], retrieval_sha256=c['content_sha256'], fact_url=facts['source_url'],
                fact_revision=facts['revision'], fact_name=facts['name'], fact_eco=facts['eco'], fact_pgn=facts['pgn'], reference_fen=c['fen'],
                scope='current_position' if ident in position_ids else 'reference_position_only',
                exact_routes=exact.get(ident,[]), bm25_score=bm25.get(ident,0), dense_score=dense_scores.get(ident),
                dense_evidence_kind=dense_info['evidence_kind'] if ident in dense_scores else 'not_used', fusion_score=value, matching_terms=matching))
            if len(citations)==3:break
        if not citations:
            reasons.append('INSUFFICIENT_DOCUMENTARY_EVIDENCE');return reply('unavailable' if errors else 'abstain')
        if any(c.scope=='reference_position_only' for c in citations):warnings.append('REFERENCES_ARE_NOT_ADVICE_FOR_THE_CURRENT_POSITION')
        if self.clock()-start > 25:
            errors.append('ADVISOR_BUDGET_EXCEEDED');return reply('unavailable')
        return reply('partial' if errors else 'ok', citations)
