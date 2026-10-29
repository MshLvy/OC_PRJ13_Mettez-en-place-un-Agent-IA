"""Mini-graphe vidéo opt-in ; aucun lien avec les exécutions d'analyse J03."""
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, Literal, TypedDict

import chess
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import RetryPolicy
from langsmith.run_helpers import tracing_context
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.positions import diagnose_fen
from app.videos import ControlledVideoQuery, Video, VideoDiscovery, VideoRequest

Topic = Literal['develop_minor_pieces', 'king_safety', 'central_control']
Intent = Literal['understand_opening', 'understand_position', 'deepen_advice']
PREFIXES = {
    'sicilienne': ('e2e4', 'c7c5'),
    'francaise': ('e2e4', 'e7e6', 'd2d4', 'd7d5'),
    'caro_kann': ('e2e4', 'c7c6', 'd2d4', 'd7d5'),
    'gambit_dame': ('d2d4', 'd7d5', 'c2c4'),
    'espagnole': ('e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5'),
    'italienne': ('e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1c4'),
}
VIDEO_BUDGET = 18.0
CALL_RESERVATION = 5.0
_GATE = Lock()


class ExploreRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['explore_videos']
    opening: Literal['espagnole', 'italienne', 'sicilienne', 'francaise', 'caro_kann', 'gambit_dame']
    fen: str = Field(min_length=1, max_length=256)
    history: list[str] | None = Field(default=None, max_length=24)
    question: str | None = Field(default=None, max_length=300)
    advice_topic: Topic | None = None
    language: Literal['fr'] = 'fr'

    @field_validator('question')
    @classmethod
    def clean_question(cls, value):
        if value is not None and any(ord(c) < 32 for c in value):
            raise ValueError('INVALID_QUESTION')
        return value.strip() or None if value is not None else None

    @model_validator(mode='after')
    def verified_position(self):
        self.fen = VideoRequest(opening=self.opening, fen=self.fen).fen
        if self.history is not None:
            board = chess.Board()
            for value in self.history:
                if len(value) > 5:
                    raise ValueError('INVALID_HISTORY')
                try:
                    move = chess.Move.from_uci(value)
                except ValueError:
                    raise ValueError('INVALID_HISTORY') from None
                if move not in board.legal_moves:
                    raise ValueError('ILLEGAL_HISTORY')
                board.push(move)
            if board.fen(en_passant='fen') != self.fen:
                raise ValueError('HISTORY_FEN_MISMATCH')
        return self


class Evidence(BaseModel):
    opening_origin: Literal['user_selected'] = 'user_selected'
    history_verified: bool = False
    opening_prefix_verified: bool = False
    rule: str | None = None
    advice_provenance: Literal['user_selected', 'rule_based'] | None = None
    side_to_move: Literal['white', 'black']


class IntentionOutcome(BaseModel):
    intent: Intent
    status: Literal['planned', 'ok', 'skipped', 'empty', 'disabled', 'unavailable']
    reason: str
    why_this_video: str
    query: str | None = Field(default=None, max_length=240)
    evidence: Evidence
    plan: ControlledVideoQuery | None = Field(default=None, exclude=True)
    video: Video | None = None


class ExplorationResponse(BaseModel):
    status: Literal['ok', 'partial', 'empty', 'disabled', 'unavailable']
    source: Literal['youtube_data_api'] = 'youtube_data_api'
    source_mode: Literal['disabled', 'synthetic_fixture', 'live']
    synthetic: bool = True
    test_transport: bool = False
    editorial_review: Literal['not_reviewed'] = 'not_reviewed'
    fen_normalized: str
    intentions: list[IntentionOutcome] = Field(min_length=3, max_length=3)
    video_count: int = Field(ge=0, le=3)
    framework: Literal['langgraph'] = 'langgraph'
    graph_version: Literal['j05_i02_video_v1'] = 'j05_i02_video_v1'
    steps: list[str]
    attempted_searches: int = Field(ge=0, le=3)
    budget_seconds: float = VIDEO_BUDGET
    deadline_mode: Literal['cooperative_between_mock_calls','cooperative_between_live_calls'] = 'cooperative_between_mock_calls'
    retries: Literal[0] = 0
    persistent_state: Literal[False] = False


class VideoState(TypedDict, total=False):
    request: ExploreRequest
    intentions: list[IntentionOutcome]
    attempted: int
    status: str


@dataclass
class VideoContext:
    adapter: VideoDiscovery
    clock: Callable[[], float]
    deadline: float


def validate_context(state: VideoState, runtime: Runtime[VideoContext]):
    # Le graphe revalide même les DTO construits hors du contrat HTTP.
    return {'request': ExploreRequest.model_validate(state['request'].model_dump()), 'attempted': 0}


def plan_intentions(state: VideoState, runtime: Runtime[VideoContext]):
    request = state['request']; diagnostic = diagnose_fen(request.fen); board = chess.Board(request.fen)
    prefix = PREFIXES[request.opening]
    recognized = request.history is not None and tuple(request.history[:len(prefix)]) == prefix
    color = board.turn
    rank = 0 if color == chess.WHITE else 7
    undeveloped = any(board.piece_at(chess.square(file, rank)) == chess.Piece(piece, color)
                      for file, piece in ((1, chess.KNIGHT), (6, chess.KNIGHT), (2, chess.BISHOP), (5, chess.BISHOP)))
    topics = {
        'develop_minor_pieces': undeveloped,
        'king_safety': board.king(color) == chess.square(4, rank) and board.has_castling_rights(color),
        'central_control': any(board.piece_at(chess.square(file, pawn_rank)) == chess.Piece(chess.PAWN, color)
                               for file in (3, 4) for pawn_rank in ((3, 4) if color else (4, 3))),
    }
    base = dict(history_verified=request.history is not None, opening_prefix_verified=recognized,
                side_to_move=diagnostic.side_to_move)
    rows = []
    def add(intent, reason, why, topic=None, provenance=None, rule=None):
        admissible = reason == 'CONTEXT_SUPPORTED'
        plan = ControlledVideoQuery(opening=request.opening, intent=intent, topic=topic) if admissible else None
        rows.append(IntentionOutcome(intent=intent, status='planned' if admissible else 'skipped',
            reason=reason, why_this_video=why, query=plan.render() if plan else None, plan=plan,
            evidence=Evidence(**base, rule=rule, advice_provenance=provenance)))
    outside = 'TERMINAL_POSITION' if diagnostic.is_terminal else 'OUTSIDE_OPENING_WINDOW' if board.fullmove_number > 12 else None
    add('understand_opening', outside or 'CONTEXT_SUPPORTED',
        'Découvrir les premiers coups et objectifs de l’ouverture explicitement choisie.')
    support = outside or ('HISTORY_REQUIRED' if request.history is None else 'OPENING_PREFIX_NOT_ESTABLISHED' if not recognized else None)
    add('understand_position', support or ('CONTEXT_SUPPORTED' if undeveloped else 'NO_DEVELOPMENT_RULE'),
        ('Étudier le développement : une pièce mineure du camp au trait est sur sa case initiale.'
         if not support and undeveloped else 'Contexte insuffisant pour proposer un thème de développement.'),
        topic='develop_minor_pieces', rule='minor_on_starting_square' if not support and undeveloped else None)
    if support:
        add('deepen_advice', support, 'Aucun conseil associé à la position sans historique admissible.')
    elif request.advice_topic is not None:
        topic = request.advice_topic
        add('deepen_advice', 'CONTEXT_SUPPORTED' if topics[topic] else 'ADVICE_NOT_SUPPORTED_BY_POSITION',
            ('Approfondir le thème choisi et admissible selon une règle limitée.' if topics[topic]
             else 'Aucune règle ne justifie le thème choisi pour cette position.'),
            topic=topic, provenance='user_selected', rule=topic if topics[topic] else None)
    elif request.question is not None:
        add('deepen_advice', 'QUESTION_IS_NOT_STRUCTURED_ADVICE',
            'Une question libre ne constitue pas un conseil échiquéen établi.')
    elif undeveloped:
        add('deepen_advice', 'CONTEXT_SUPPORTED',
            'Approfondir le principe de développement admissible sans question préalable.',
            topic='develop_minor_pieces', provenance='rule_based', rule='minor_on_starting_square')
    else:
        add('deepen_advice', 'NO_ADMISSIBLE_ADVICE', 'Aucun principe déterministe admissible pour ce parcours.')
    return {'intentions': rows}


def search_intentions(state: VideoState, runtime: Runtime[VideoContext]):
    seen = set(); outcomes = []; attempted = 0; halted=None
    for row in state['intentions']:
        row = row.model_copy(deep=True)
        if row.status == 'planned':
            if runtime.context.adapter.mode == 'disabled':
                row.status = 'disabled'; row.reason = 'YOUTUBE_DISABLED'
            elif halted:
                row.status='unavailable';row.reason=halted
            elif runtime.context.clock() + CALL_RESERVATION > runtime.context.deadline:
                row.status = 'unavailable'; row.reason = 'VIDEO_DEADLINE_EXCEEDED'
            else:
                attempted += 1
                try:
                    result = runtime.context.adapter.search_plan(row.plan)
                    if runtime.context.clock() > runtime.context.deadline:
                        row.status = 'unavailable'; row.reason = 'VIDEO_DEADLINE_EXCEEDED'
                    else:
                        candidate = next((v for v in result.videos if v.video_id not in seen), None)
                        if result.status == 'ok' and candidate is not None:
                            row.status = 'ok'; row.reason = 'LIVE_CANDIDATE_SELECTED' if runtime.context.adapter.mode=='live' else 'SYNTHETIC_CANDIDATE_SELECTED'
                            row.video = candidate; seen.add(candidate.video_id)
                        else:
                            row.status = 'empty' if result.status == 'ok' else result.status
                            row.reason = result.code or ('GLOBAL_DUPLICATE_CANDIDATES' if result.videos else 'NO_ACCEPTABLE_CANDIDATES')
                            if runtime.context.adapter.mode=='live' and result.code in ('YOUTUBE_QUOTA_EXCEEDED','YOUTUBE_RATE_LIMITED','YOUTUBE_AUTHORIZATION_FAILED','YOUTUBE_KEY_UNAVAILABLE','YOUTUBE_LOCAL_RATE_LIMITED','YOUTUBE_LIVE_BUSY'):
                                halted=result.code
                except Exception:
                    row.status = 'unavailable'; row.reason = 'VIDEO_ADAPTER_ERROR'
        outcomes.append(row)
    return {'intentions': outcomes, 'attempted': attempted}


def assemble_response(state: VideoState, runtime: Runtime[VideoContext]):
    statuses = [r.status for r in state['intentions']]
    count = statuses.count('ok')
    active = [s for s in statuses if s != 'skipped']
    status = ('ok' if count == 3 else 'partial' if count else 'disabled' if active and all(s == 'disabled' for s in active)
              else 'unavailable' if 'unavailable' in active else 'empty')
    return {'status': status}


def build_video_graph():
    builder = StateGraph(VideoState, context_schema=VideoContext)
    nodes = (validate_context, plan_intentions, search_intentions, assemble_response)
    previous = START
    for node in nodes:
        builder.add_node(node.__name__, node, retry_policy=RetryPolicy(max_attempts=1))
        builder.add_edge(previous, node.__name__); previous = node.__name__
    builder.add_edge(previous, END)
    return builder.compile(checkpointer=None, name='video_exploration_i02')


class VideoExplorationBusy(Exception):
    pass


class VideoExploration:
    def __init__(self, adapter, clock=monotonic, gate=None):
        self.adapter, self.clock, self.gate = adapter, clock, gate if gate is not None else _GATE
        self.graph = build_video_graph()

    def invoke(self, request: ExploreRequest):
        if not self.gate.acquire(blocking=False):
            raise VideoExplorationBusy('VIDEO_EXPLORATION_BUSY')
        try:
            state = VideoState(request=request)
            context = VideoContext(self.adapter, self.clock, self.clock() + VIDEO_BUDGET)
            steps = []
            with tracing_context(enabled=False):
                for update in self.graph.stream(state, context=context, stream_mode='updates',
                        config={'recursion_limit': 6, 'max_concurrency': 1, 'callbacks': []}):
                    for name, value in update.items():
                        steps.append(name); state.update(value)
            rows = state['intentions']
            return ExplorationResponse(status=state['status'], source_mode=self.adapter.mode,
                synthetic=self.adapter.mode!='live',test_transport=self.adapter.test_transport,
                deadline_mode='cooperative_between_live_calls' if self.adapter.mode=='live' else 'cooperative_between_mock_calls',
                fen_normalized=state['request'].fen, intentions=rows,
                video_count=sum(r.video is not None for r in rows), steps=steps, attempted_searches=state['attempted'])
        finally:
            self.gate.release()
