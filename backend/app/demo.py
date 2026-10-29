"""Façade locale de démonstration, isolée des contrats historiques.

Aucune I/O au boot. Simulation intégralement locale ; live sous plafonds hérités.
Le client ne choisit ni fournisseur, ni chemin de moteur, ni autorisation.
"""
from app.workflow_dispatch import dispatch

from collections import OrderedDict
from dataclasses import dataclass, replace
import ipaddress
import os
from threading import Lock
from time import monotonic
from typing import Literal
from urllib.parse import urlsplit

import chess
import chess.engine
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, model_validator

from app.config import StockfishSettings
from app.evaluate_routes import EvaluationResponse
from app.explorer_registry import UnavailableLiveExplorer
from app.explorer import ExplorerError, GameStats, MovesResult, ObservedMove, OpeningExplorer
from app.game import Choice, GameError, GameService, HistoryRequest, TurnRequest, TurnResponse, rebuild, snapshot
from app.game_routes import GameRoute
from app.orchestration import AnalysisOrchestrator, AnalysisResponse, EngineOutcome, ToolOutcomes, OrchestrationError, GraphGate
from app.stockfish import RawEvaluation, StockfishService, StockfishError, EngineGate

DemoMode = Literal['simulation', 'live']


def env_bool(name):
    value = os.getenv(name, 'false')
    if value not in ('true', 'false'):
        raise ValueError('INVALID_' + name)
    return value == 'true'


@dataclass(frozen=True)
class DemoSettings:
    enabled: bool = False
    allow_live: bool = False

    @classmethod
    def from_env(cls):
        settings = cls(env_bool('DEMO_ENABLED'), env_bool('DEMO_ALLOW_LIVE'))
        if settings.allow_live and not settings.enabled:
            raise ValueError('DEMO_LIVE_REQUIRES_DEMO')
        return settings


class Capabilities(BaseModel):
    demo_enabled: bool
    allowed_modes: list[DemoMode]
    default_mode: Literal['simulation'] = 'simulation'
    locked_mode: Literal['legacy_offline'] = 'legacy_offline'
    live_reasons: list[str]
    explorer: str
    engine: str
    min_live_interval_seconds: int = 2
    max_live_interactions_per_hour: int = 120
    retries: Literal[0] = 0


class DemoTurnRequest(TurnRequest):
    demo_mode: DemoMode

    @model_validator(mode='before')
    @classmethod
    def server_source_only(cls, data):
        if isinstance(data, dict) and 'source' in data:
            raise ValueError('DEMO_SOURCE_IS_SERVER_SELECTED')
        return data


class DemoAnalysisRequest(HistoryRequest):
    demo_mode: DemoMode
    fen: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=0, le=256, strict=True)
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')


class DemoEvaluation(EvaluationResponse):
    source_mode: Literal['synthetic_fixture', 'local_engine']


class DemoEngineOutcome(EngineOutcome):
    result: DemoEvaluation | None = None


class DemoTools(ToolOutcomes):
    engine: DemoEngineOutcome


class DemoAnalysis(AnalysisResponse):
    tools: DemoTools


class DemoAnalysisResponse(BaseModel):
    demo_mode: DemoMode
    simulation: bool
    data: DemoAnalysis


class DemoTurnResponse(BaseModel):
    demo_mode: DemoMode
    simulation: bool
    data: TurnResponse


# Petites positions de fixture connues, sans prétention théorique.
_LINE = ['e2e4', 'c7c5', 'g1f3', 'd7d6', 'd2d4', 'c5d4', 'f3d4', 'g8f6']
_KNOWN = set()
_board = chess.Board()
_KNOWN.add(_board.fen(en_passant='fen'))
for _uci in _LINE:
    _board.push_uci(_uci)
    _KNOWN.add(_board.fen(en_passant='fen'))


class FixtureExplorer(OpeningExplorer):
    source_mode = 'synthetic_fixture'

    def __init__(self):
        super().__init__(None, 'synthetic_fixture')

    def moves(self, fen):
        board = chess.Board(fen)
        moves = []
        if fen not in _KNOWN:raise ExplorerError('SIMULATION_NO_POSITION_DATA',503)
        if fen in _KNOWN:
            for index, move in enumerate(sorted(board.legal_moves, key=lambda m: m.uci())[:2]):
                moves.append(ObservedMove(move.uci(), board.san(move), GameStats(6 + index, 2, 2, 10 + index)))
        return MovesResult('ok' if moves else 'empty', fen, self.source_mode,
                           GameStats(13, 4, 4, 21) if moves else None, moves)


async def fixture_engine(settings, board, gate):
    # Ce runner ne crée JAMAIS de processus, même si le serveur live est autorisé.
    move = sorted(board.legal_moves, key=lambda m: m.uci())[0]
    return RawEvaluation({'score': chess.engine.PovScore(chess.engine.Cp(35), chess.WHITE), 'depth': 8},
                         move, 'Stockfish fixture')


class MissingFixtureEngine:
    def evaluate(self, fen):
        raise StockfishError('SIMULATION_NO_POSITION_DATA', 503)


class FixtureEngine(StockfishService):
    def evaluate(self, fen):
        if fen not in _KNOWN:
            return MissingFixtureEngine().evaluate(fen)
        return super().evaluate(fen)


class DemoFixtureGame(GameService):
    """Only explicit move fixtures in this facade; legacy game route unchanged."""
    def choose(self,board,history,source,deadline):
        lines=[_LINE+['b1c3','a7a6'],['d2d4','d7d5','c2c4','e7e6']]
        if source=='synthetic_fixture' and not any(history==line[:len(history)] and len(history)<len(line) for line in lines):
            return None,Choice(source='none',source_mode='unavailable',reason='SIMULATION_NO_POSITION_DATA',synthetic=False),['SIMULATION_NO_POSITION_DATA']
        return super().choose(board,history,source,deadline)


class BoundedExplorer:
    """Cache commun jeu/analyse, 429 respecté globalement, pas de retry caché."""
    source_mode = 'live'

    def __init__(self, delegate, clock=monotonic):
        self.delegate, self.clock = delegate, clock
        self.cache = OrderedDict()
        self.blocked_until = 0.0

    def moves(self, fen):
        now = self.clock()
        cached = self.cache.get(fen)
        if cached and now - cached[0] < 30:
            if isinstance(cached[1], ExplorerError):
                raise cached[1]
            return cached[1]
        if now < self.blocked_until:
            raise ExplorerError('UPSTREAM_RATE_LIMITED', 503, int(self.blocked_until - now) + 1)
        try:
            result = self.delegate.moves(fen)
            if result.source_mode != 'live':
                raise ExplorerError('DEMO_AUTHENTIC_SOURCE_REQUIRED', 503)
        except ExplorerError as error:
            if error.code == 'UPSTREAM_RATE_LIMITED':
                self.blocked_until = now + (error.retry_after if error.retry_after is not None else 60)
            self._save(fen, error, now)
            raise
        self._save(fen, result, now)
        return result

    def _save(self, fen, result, now):
        self.cache[fen] = (now, result)
        self.cache.move_to_end(fen)
        if len(self.cache) > 64:
            self.cache.popitem(last=False)


class FrequencyExplorer:
    """Choix adverse seulement : pas de fréquence inventée si comptes absents."""
    source_mode = 'live'

    def __init__(self, delegate):
        self.delegate = delegate

    def moves(self, fen):
        result = self.delegate.moves(fen)
        eligible = [m for m in result.moves if m.statistics and m.statistics.games > 0]
        return replace(result, moves=eligible, status='ok' if eligible else 'empty')


class DemoService:
    def __init__(self, settings, demo_settings, explorers, engine, allow_game, *, clock=monotonic):
        self.settings, self.config = settings, demo_settings
        self.engine, self.allow_game, self.clock = engine, allow_game, clock
        self.gate = Lock()
        self.last_live = {}
        self.live_window = clock()
        self.live_count = 0
        self.live_explorer = BoundedExplorer(explorers.get('live', UnavailableLiveExplorer('LICHESS_CONFIGURATION_UNAVAILABLE')) if settings.explorer_mode=='live' else UnavailableLiveExplorer('LICHESS_CONFIGURATION_UNAVAILABLE'), clock)
        sim_explorer = FixtureExplorer()
        sim_engine = FixtureEngine(StockfishSettings(enabled=True), runner=fixture_engine, gate=EngineGate())
        sim_settings = replace(settings, explorer_mode='synthetic_fixture', explorer_default_mode='disabled',
                               stockfish=sim_engine.settings, analysis_default_engine=False)
        self.sim_graph = AnalysisOrchestrator(sim_explorer, sim_engine, settings=sim_settings,
                                              explorers={'synthetic_fixture': sim_explorer}, gate=GraphGate())
        self.sim_game = DemoFixtureGame(sim_explorer, sim_engine)
        self.live_graph = AnalysisOrchestrator(self.live_explorer, engine, settings=settings,
                                               explorers={**explorers, 'live': self.live_explorer})
        self.live_game = GameService(FrequencyExplorer(self.live_explorer), engine, allow_tools=allow_game)

    def capabilities(self):
        reasons = []
        if not self.config.allow_live: reasons.append('DEMO_LIVE_DISABLED')
        if self.settings.explorer_mode != 'live': reasons.append('EXPLORER_LIVE_NOT_ALLOWED')
        if not self.settings.stockfish.enabled: reasons.append('STOCKFISH_NOT_ALLOWED')
        if not self.allow_game: reasons.append('GAME_TOOLS_DISABLED')
        return Capabilities(demo_enabled=self.config.enabled,
            allowed_modes=(['simulation'] + (['live'] if self.config.allow_live else [])) if self.config.enabled else [],
            live_reasons=reasons,
            explorer=('configuration_unavailable' if isinstance(self.live_explorer.delegate,UnavailableLiveExplorer) else 'authorized_not_probed') if self.settings.explorer_mode == 'live' else 'disabled',
            engine=('binary_present_not_probed' if os.path.isfile(self.settings.stockfish.path) and os.access(self.settings.stockfish.path, os.X_OK)
                    else 'binary_missing') if self.settings.stockfish.enabled else 'disabled')

    def authorize(self, mode):
        if not self.config.enabled: raise GameError('DEMO_DISABLED', 403)
        if mode not in self.capabilities().allowed_modes: raise GameError('DEMO_LIVE_NOT_ALLOWED', 403)

    def run(self, mode, kind, call):
        self.authorize(mode)
        # Une interaction de démo dans le worker, y compris jeu vs analyse.
        # Aucun thread abandonné ; les verrous historiques protègent aussi les anciennes routes.
        if not self.gate.acquire(blocking=False): raise GameError('DEMO_BUSY', 503)
        try:
            if mode == 'live':
                now = self.clock()
                if now - self.live_window >= 3600:
                    self.live_window, self.live_count = now, 0
                if now - self.last_live.get(kind, float('-inf')) < 2 or self.live_count >= 120:
                    raise GameError('DEMO_RATE_LIMITED', 429)
                self.last_live[kind] = now
                self.live_count += 1
            return call()
        finally:
            self.gate.release()

    def turn(self, body):
        # Les sources de la requête cliente sont rejetées, source canonique serveur uniquement.
        request = TurnRequest.model_validate({**body.model_dump(exclude={'demo_mode', 'source'}),
            'source': 'synthetic_fixture' if body.demo_mode == 'simulation' else 'theory_then_engine'})
        game = self.sim_game if body.demo_mode == 'simulation' else self.live_game
        return self.run(body.demo_mode, 'turn', lambda: DemoTurnResponse(demo_mode=body.demo_mode,
                        simulation=body.demo_mode == 'simulation', data=game.turn(request)))

    def analysis(self, body):
        board, _ = rebuild(body.history)
        if body.revision != len(body.history) or body.snapshot != snapshot(body.history):
            raise GameError('GAME_SNAPSHOT_MISMATCH', 409)
        if board.fen(en_passant='fen') != body.fen: raise GameError('DEMO_FEN_MISMATCH', 409)
        def call():
            sim = body.demo_mode == 'simulation'
            explorer_allowed=sim or self.settings.explorer_mode=='live'
            engine_allowed=sim or self.settings.stockfish.enabled
            data = (self.sim_graph if sim else self.live_graph).invoke(body.fen,
                explorer_mode='synthetic_fixture' if sim else 'live' if explorer_allowed else 'disabled', include_engine=engine_allowed).model_dump()
            # The demo asks for both; execute only under each historical server ceiling.
            # Graph preferences/steps retain the actual resolved calls, not invented I/O.
            for tool,allowed,code in [('explorer',explorer_allowed,'EXPLORER_LIVE_NOT_ALLOWED'),('engine',engine_allowed,'STOCKFISH_NOT_ALLOWED')]:
                if not allowed:
                    data['tools'][tool].update(requested=True,status='disabled',http_status=403,result=None)
                    data['errors'].append({'tool':tool,'code':code,'http_status':403,'retry_after_seconds':None})
                    data['provenance'].append({'tool':tool,'source':'stockfish' if tool=='engine' else 'lichess_opening_explorer','source_mode':'disabled','attempted':False,'engine_version':None})
                    data['status']='partial' if data['status']!='terminal' else 'terminal'
            if sim:
                if data['tools']['engine']['result']:
                    data['tools']['engine']['result']['source_mode'] = 'synthetic_fixture'
                for p in data['provenance']:
                    if p['tool'] == 'engine': p['source_mode'] = 'synthetic_fixture'
            return DemoAnalysisResponse(demo_mode=body.demo_mode, simulation=sim, data=DemoAnalysis.model_validate(data))
        return self.run(body.demo_mode, 'analysis', call)


class DemoRoute(GameRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            # Host/Origin ne sont PAS une authentification. Ne fait pas confiance à X-Forwarded-For.
            try:
                local = ipaddress.ip_address(request.client.host).is_loopback
            except (ValueError, AttributeError): local = False
            # Exact opt-in peer on the dedicated Compose network; never a CIDR wildcard.
            proxy = os.environ.get('DEMO_TRUSTED_PROXY_IP')
            trusted = bool(proxy and request.client and request.client.host == proxy
                           and proxy == '172.30.73.2')
            if not local and not trusted:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={'detail': {'code': 'DEMO_LOCAL_ONLY'}})
            if request.headers.get('forwarded') or request.headers.get('x-forwarded-for'):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={'detail': {'code': 'DEMO_FORWARDED_NOT_ALLOWED'}})
            origin = request.headers.get('origin')
            allowed_origin = origin in ('http://127.0.0.1:5173', 'http://localhost:5173')
            if (trusted and not allowed_origin) or (origin and urlsplit(origin).hostname not in ('127.0.0.1', 'localhost', '::1')):
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=403, content={'detail': {'code': 'DEMO_ORIGIN_REJECTED'}})
            try:
                return await original(request)
            except OrchestrationError as error:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=error.http_status, content={'detail': {'code': error.code}})
        return handler


router = APIRouter(prefix='/api/v1/demo', tags=['demo'], route_class=DemoRoute)


@router.get('/capabilities', response_model=Capabilities)
def capabilities(request: Request):
    return request.app.state.demo.capabilities()


@router.post('/turn', response_model=DemoTurnResponse)
def turn(body: DemoTurnRequest, request: Request):
    return dispatch(request, 'demo_turn', body=body)


@router.post('/analysis', response_model=DemoAnalysisResponse)
def analysis(body: DemoAnalysisRequest, request: Request):
    return dispatch(request, 'demo_analysis', body=body)
