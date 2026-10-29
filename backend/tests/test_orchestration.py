"""Vrai runtime LangGraph ; outils et I/O simulés, jamais de fournisseur/moteur réel."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import chess
import chess.engine
import httpx2 as httpx
from fastapi.testclient import TestClient
from langgraph.graph.state import CompiledStateGraph
from langsmith import utils as tracing_utils
import pytest

from app import orchestration as og
from app.config import StockfishSettings, Settings
from app.analysis_preferences import PreferenceError
from app.explorer import ExplorerError, MovesResult, OpeningExplorer
from app.main import create_app
from app.positions import FenValidationError
from app.stockfish import EngineGate, RawEvaluation, StockfishError, StockfishService

INITIAL = chess.STARTING_FEN
TERMINALS = [
    '7k/6Q1/6K1/8/8/8/8/8 b - - 0 1',  # mat
    '7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',  # pat
    '7k/8/6K1/8/8/8/8/8 w - - 0 1',   # matériel insuffisant
    INITIAL.replace(' 0 1', ' 150 80'),  #75 coups, historique non disponible
]


@pytest.fixture(autouse=True)
def graph_gate(monkeypatch):
    monkeypatch.setattr(og, '_GLOBAL_GATE', og.GraphGate())


class Clock:
    now = 0.0
    def __call__(self):
        return self.now


def make_service(*, explorer_error=None, engine_error=None, clock=None, empty=False):
    calls = []
    def transport(request):
        calls.append('explorer')
        if explorer_error:
            raise explorer_error
        return httpx.Response(200, json={'moves': [] if empty else [{'uci': 'e2e4'}]})
    explorer = OpeningExplorer(httpx.Client(transport=httpx.MockTransport(transport)), 'injected_transport')
    async def runner(settings, board, gate):
        calls.append('engine')
        assert not tracing_utils.tracing_is_enabled()
        if engine_error:
            raise engine_error
        return RawEvaluation({'score': chess.engine.PovScore(chess.engine.Cp(42), board.turn), 'depth': 8},
                             chess.Move.from_uci('d2d4'), 'Stockfish simulated')
    engine = StockfishService(StockfishSettings(True), runner=runner, gate=EngineGate())
    orchestrator = og.AnalysisOrchestrator(explorer, engine,
        settings=Settings("simulated", explorer_mode="live", stockfish=StockfishSettings(True)),
        clock=clock or og.monotonic)
    return orchestrator, calls


@pytest.mark.parametrize('explorer,engine,steps,calls', [
    (False, False, ['validate_position','assemble_response'], []),
    (True, False, ['validate_position','fetch_explorer','assemble_response'], ['explorer']),
    (False, True, ['validate_position','evaluate_engine','assemble_response'], ['engine']),
    (True, True, ['validate_position','fetch_explorer','evaluate_engine','assemble_response'], ['explorer','engine']),
])
def test_compiled_graph_transitions_and_non_invocations(explorer, engine, steps, calls):
    service, seen = make_service()
    assert isinstance(service.graph, CompiledStateGraph)
    assert service.graph.checkpointer is None
    assert seen == []  # Construction/compilation sans appel.
    result = service.invoke(INITIAL, explorer, engine)
    assert result.status == 'ok' and result.errors == []
    assert result.graph.steps == steps and seen == calls
    assert result.tools.explorer.status == ('ok' if explorer else 'not_requested')
    assert result.tools.engine.status == ('ok' if engine else 'not_requested')
    assert [p.tool for p in result.provenance] == ['position'] + calls
    assert result.position.repetition_status == 'unknown_without_history'
    assert result.policy.retries == 0 and not result.policy.persistent_state


@pytest.mark.parametrize('fen', TERMINALS)
def test_terminal_never_invokes_tools_even_when_requested(fen):
    service, calls = make_service()
    result = service.invoke(fen, True, True)
    assert result.status == 'terminal' and result.position.is_terminal
    assert result.tools.engine.status == result.tools.explorer.status == 'skipped_terminal'
    assert result.tools.engine.result is result.tools.explorer.result is None
    assert result.graph.steps == ['validate_position','assemble_response']
    assert calls == [] and len(result.provenance) == 1 and result.errors == []


@pytest.mark.parametrize('fen,code', [('broken','INVALID_FEN_FORMAT'),('8/8/8/8/8/8/8/8 w - - 0 1','INVALID_POSITION')])
def test_fen_error_before_any_tool_or_admission(fen, code):
    service, calls = make_service()
    assert service.gate.lock.acquire(False)
    with pytest.raises(FenValidationError, match=code):
        service.invoke(fen, True, True)
    assert calls == []
    service.gate.lock.release()


def test_empty_is_success_not_theory_fallback():
    service, calls = make_service(empty=True)
    result = service.invoke(INITIAL, True)
    assert result.status == 'ok' and result.tools.explorer.status == 'empty'
    assert result.tools.explorer.result.moves == [] and result.errors == []
    assert calls == ['explorer'] and result.tools.engine.status == 'not_requested'
    assert 'theory' not in result.model_dump_json()


@pytest.mark.parametrize('status,code,http_status', [
    (401,'UPSTREAM_AUTHORIZATION_FAILED',502), (403,'UPSTREAM_AUTHORIZATION_FAILED',502),
    (429,'UPSTREAM_RATE_LIMITED',503), (500,'UPSTREAM_UNAVAILABLE',503),
    (301,'UPSTREAM_INVALID_RESPONSE',502),
])
def test_provider_status_preserved_per_tool_and_engine_still_runs(status, code, http_status):
    service, calls = make_service()
    def transport(request):
        calls.append('explorer')
        return httpx.Response(status, headers={'Retry-After': '7'})
    service.explorer.client.close()
    service.explorer.client = httpx.Client(transport=httpx.MockTransport(transport))
    result = service.invoke(INITIAL, True, True)
    assert result.status == 'partial' and calls == ['explorer','engine']
    assert result.tools.explorer.status == 'error' and result.tools.explorer.http_status == http_status
    assert result.tools.engine.status == 'ok'
    assert result.errors[0].code == code and result.errors[0].tool == 'explorer'
    assert result.errors[0].retry_after_seconds == (7 if status == 429 else None)


@pytest.mark.parametrize('error,code', [
    (httpx.ReadTimeout('simulated'), 'UPSTREAM_TIMEOUT'),
    (httpx.ConnectError('simulated'), 'UPSTREAM_UNAVAILABLE'),
])
def test_provider_transport_failure_is_not_empty(error, code):
    service, calls = make_service(explorer_error=error)
    result = service.invoke(INITIAL, True)
    assert result.errors[0].code == code and result.tools.explorer.result is None
    assert result.tools.explorer.status == 'error' and calls == ['explorer']


@pytest.mark.parametrize('code,status', [
    ('STOCKFISH_DISABLED',503), ('STOCKFISH_NOT_FOUND',503), ('STOCKFISH_UNAVAILABLE',503),
    ('STOCKFISH_BUSY',503), ('STOCKFISH_TIMEOUT',504), ('STOCKFISH_PROTOCOL_ERROR',502),
    ('STOCKFISH_CLEANUP_FAILED',503),
])
def test_engine_errors_preserve_explorer_result(code, status):
    service, calls = make_service(engine_error=StockfishError(code,status))
    result = service.invoke(INITIAL, True, True)
    assert result.status == 'partial' and calls == ['explorer','engine']
    assert result.tools.explorer.result.moves[0].san == 'e4'
    assert result.tools.engine.http_status == status and result.errors[0].code == code
    assert result.tools.engine.status == ('disabled' if code.endswith('DISABLED') else 'error')
    assert result.errors[0].tool == 'engine'


def test_disabled_both_refused_before_tools():
    # I04bis : dépassement de plafond, plus un faux incident technique partial.
    service = og.AnalysisOrchestrator(OpeningExplorer(None), StockfishService(StockfishSettings()))
    with pytest.raises(PreferenceError, match="EXPLORER_MODE_NOT_ALLOWED"):
        service.invoke(INITIAL, True, True)
    assert not service.gate.lock.locked()


@pytest.mark.parametrize('which', ['explorer','engine'])
def test_unexpected_exception_does_not_leak_secret_and_other_tool_continues(which):
    secret = 'private-simulated-value-never-in-state'
    service, calls = make_service(**{which+'_error': RuntimeError(secret)})
    result = service.invoke(INITIAL, True, True)
    assert result.status == 'partial' and calls == ['explorer','engine']
    assert result.errors[0].code == ('EXPLORER' if which == 'explorer' else 'STOCKFISH')+'_INTERNAL_ERROR'
    assert secret not in result.model_dump_json()


def test_deadline_reserves_full_next_tool_budget_without_invocation(monkeypatch):
    clock = Clock()
    service, calls = make_service(clock=clock)
    original = service.explorer.moves
    def slow(fen):
        result = original(fen)
        clock.now = 16.0  # Temps simulé ; aucun sleep ni vrai I/O.
        return result
    monkeypatch.setattr(service.explorer, 'moves', slow)
    result = service.invoke(INITIAL, True, True)
    assert calls == ['explorer'] and result.tools.explorer.status == 'ok'
    assert result.errors[0].code == 'ORCHESTRATION_DEADLINE_EXCEEDED'
    assert result.errors[0].tool == 'engine' and result.errors[0].http_status == 504
    assert result.provenance[-1].attempted is False and result.status == 'partial'
    assert not service.gate.lock.locked()


def test_deadline_overrun_keeps_completed_results_and_reports_it(monkeypatch):
    clock = Clock()
    service, calls = make_service(clock=clock)
    original = service.explorer.moves
    def slow(fen):
        result = original(fen)
        clock.now = 21.0
        return result
    monkeypatch.setattr(service.explorer, 'moves', slow)
    result = service.invoke(INITIAL, True)
    assert result.tools.explorer.status == 'ok' and calls == ['explorer']
    assert result.status == 'partial' and result.errors[0].tool == 'orchestration'


def test_concurrency_refused_without_queue_but_diagnostic_stays_available(monkeypatch):
    entered, release = Event(), Event()
    service, calls = make_service()
    original = service.explorer.moves
    def blocked(fen):
        entered.set()
        assert release.wait(3)
        return original(fen)
    monkeypatch.setattr(service.explorer, 'moves', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.invoke, INITIAL, True, False)
        try:
            assert entered.wait(3)
            with pytest.raises(og.OrchestrationError, match='ORCHESTRATION_BUSY'):
                service.invoke(INITIAL, False, True)
            assert service.invoke(INITIAL).status == 'ok'
            assert service.invoke(TERMINALS[0],True,True).status == 'terminal'
            assert calls == []
        finally:
            release.set()
        assert future.result().status == 'ok'
    assert calls == ['explorer'] and not service.gate.lock.locked()
    assert service.invoke(INITIAL,False,True).tools.engine.status == 'ok'


def test_each_request_has_independent_ephemeral_state_and_normalized_fen():
    service, calls = make_service()
    first = service.invoke('  '+INITIAL.replace(' ', '  ')+'  ',True,True)
    assert first.fen_normalized == INITIAL
    second = service.invoke(INITIAL)
    assert second.errors == [] and len(second.provenance) == 1
    assert second.tools.engine.result is second.tools.explorer.result is None
    assert first.tools.engine.result is not None and calls == ['explorer','engine']


def test_real_runtime_disables_hosted_tracing_even_when_environment_requests_it(monkeypatch):
    monkeypatch.setenv('LANGSMITH_TRACING','true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2','true')
    monkeypatch.setenv('LANGSMITH_API_KEY','simulated-private-tracing-token')
    service, calls = make_service()
    result = service.invoke(INITIAL,False,True)  # Runner asserts tracing disabled.
    assert result.status == 'ok' and calls == ['engine']
    assert 'simulated-private' not in result.model_dump_json()


@pytest.mark.parametrize('body', [
    {}, {'fen':1}, {'fen':INITIAL,'include_engine':'true'},
    {'fen':INITIAL,'include_explorer':1}, {'fen':INITIAL,'include_engine':None},
    {'fen':INITIAL,'unexpected':'no'}, {'fen':'x'*257},
])
def test_http_strict_request_rejected_before_tools(body):
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/analysis/orchestrate',json=body)
        assert response.status_code == 422


@pytest.mark.parametrize('fen,code',[('broken','INVALID_FEN_FORMAT'),('8/8/8/8/8/8/8/8 w - - 0 1','INVALID_POSITION')])
def test_http_fen_errors_match_shared_codes(fen, code):
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/analysis/orchestrate',json={'fen':fen,'include_engine':True,'include_explorer':True})
        assert response.status_code == 422 and response.json()['detail']['code'] == code


def test_http_defaults_partial_contract_provenance_and_openapi(monkeypatch):
    monkeypatch.setenv('LICHESS_API_TOKEN','simulated-secret-unused-by-mock')
    monkeypatch.setenv('EXPLORER_MODE','live')
    monkeypatch.setenv('STOCKFISH_ENABLED','true')
    async def failed_engine(*args):
        raise StockfishError('STOCKFISH_UNAVAILABLE',503)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as transport:
      with TestClient(create_app(transport, failed_engine)) as client:
        response = client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL})
        assert response.status_code == 200
        assert response.json()['graph']['steps'] == ['validate_position','assemble_response']
        partial = client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'include_engine':True,'include_explorer':True})
        assert partial.status_code == 200 and partial.json()['status'] == 'partial'
        assert [e['http_status'] for e in partial.json()['errors']] == [503,503]
        assert 'simulated-secret' not in partial.text
        schema = client.get('/openapi.json').json()
        request = schema['components']['schemas']['AnalysisRequest']
        # L'omission hérite maintenant du serveur, pas un booléen false figé.
        assert 'default' not in request['properties']['include_engine']
        assert 'default' not in request['properties']['include_explorer']
        assert request['properties']['include_engine']['type'] == 'boolean'
        assert request['additionalProperties'] is False
        for path in ('/api/v1/moves/{fen}', '/api/v1/evaluate/{fen}', '/api/v1/positions/validate', '/api/v1/healthcheck'):
            assert path in schema['paths']
        assert schema['paths']['/api/v1/analysis/orchestrate']['post']['responses']['200']


def test_http_graph_busy_503_releases_no_foreign_lock(monkeypatch):
    monkeypatch.setenv("STOCKFISH_ENABLED", "true")
    app = create_app()
    service = app.state.orchestrator
    service.gate.lock.acquire()
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'include_engine':True})
            assert response.status_code == 503 and response.json()['detail']['code'] == 'ORCHESTRATION_BUSY'
            assert service.gate.lock.locked()
    finally:
        service.gate.lock.release()
