"""UCI et API entièrement simulés ; aucun vrai processus moteur dans pytest."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from urllib.parse import quote

import chess
import chess.engine
import pytest
from fastapi.testclient import TestClient

from app.config import StockfishSettings, Settings
from app.main import create_app
from app.positions import FenValidationError
from app import stockfish as sf

INITIAL = chess.STARTING_FEN
BLACK_INITIAL = INITIAL.replace(' w ', ' b ')
SPAWN_FACTORY = sf.spawn_engine  # Factory réelle, son popen sera mocké dans le seul test d'argv.


@pytest.fixture(autouse=True)
def isolated_gate(monkeypatch):
    monkeypatch.setattr(sf, '_GLOBAL_GATE', sf.EngineGate())


def raw(board=None, score=None, **info):
    board = board or chess.Board()
    move = next(iter(board.legal_moves))
    return sf.RawEvaluation({'score': score or chess.engine.PovScore(chess.engine.Cp(37), board.turn),
                             'depth': 12, **info}, move, 'Stockfish simulated')


def service(result=None):
    calls = []

    async def runner(settings, board, gate):
        calls.append((settings, board, gate))
        if isinstance(result, Exception):
            raise result
        return result or raw(board)

    return sf.StockfishService(StockfishSettings(True), runner=runner), calls


@pytest.mark.parametrize('fen', ['bad fen', INITIAL.split()[0], '7k/8/8/8/8/8/8/8 w - - 0 1'])
def test_invalid_fen_before_runner(fen):
    engine, calls = service()
    with pytest.raises(FenValidationError):
        engine.evaluate(fen)
    assert not calls


@pytest.mark.parametrize('fen,termination', [
    ('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1', 'checkmate'),
    ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1', 'stalemate'),
    ('7k/8/6K1/8/8/8/8/8 w - - 0 1', 'insufficient_material'),
    (INITIAL.replace(' 0 1', ' 150 100'), 'seventyfive_moves'),
])
def test_terminal_no_spawn_even_disabled(fen, termination):
    engine = sf.StockfishService(StockfishSettings(False))
    result = engine.evaluate(fen)
    assert result.status == 'terminal' and result.position.termination == termination
    assert result.score is result.best_move_uci is result.best_move_san is result.depth is result.engine_version is None
    assert not result.limits.analysis_applied and not result.position.history_available


def test_disabled_and_busy_are_distinct():
    with pytest.raises(sf.StockfishError, match='STOCKFISH_DISABLED') as error:
        sf.StockfishService(StockfishSettings()).evaluate(INITIAL)
    assert error.value.http_status == 503
    engine, calls = service()
    engine.gate.lock.acquire()
    try:
        with pytest.raises(sf.StockfishError, match='STOCKFISH_BUSY'):
            engine.evaluate(INITIAL)
    finally:
        engine.gate.lock.release()
    assert not calls


@pytest.mark.parametrize('turn,score,expected_type,expected', [
    (chess.WHITE, chess.engine.Cp(70), 'cp', 70),
    (chess.BLACK, chess.engine.Cp(70), 'cp', -70),
    (chess.WHITE, chess.engine.Mate(3), 'mate', 3),
    (chess.BLACK, chess.engine.Mate(3), 'mate', -3),
    (chess.BLACK, chess.engine.Mate(-2), 'mate', 2),
])
def test_scores_always_white_perspective_and_legal_san(turn, score, expected_type, expected):
    fen = INITIAL if turn else BLACK_INITIAL
    board = chess.Board(fen)
    engine, _ = service(raw(board, chess.engine.PovScore(score, turn)))
    result = engine.evaluate(fen)
    assert (result.score.type, result.score.value, result.score.perspective) == (expected_type, expected, 'white')
    move = chess.Move.from_uci(result.best_move_uci)
    assert board.is_legal(move) and result.best_move_san == board.san(move)
    assert result.limits.threads == 1 and result.limits.hash_mb == 16 and result.limits.multipv == 1
    assert result.limits.time_seconds == 0.5 and result.limits.depth == 20 and result.depth == 12


@pytest.mark.parametrize('turn,flags,expected', [(chess.WHITE, {'lowerbound': True}, 'lower'),
                                                (chess.BLACK, {'lowerbound': True}, 'upper'),
                                                (chess.BLACK, {'upperbound': True}, 'lower')])
def test_score_bounds_follow_score_pov(turn, flags, expected):
    result = raw(score=chess.engine.PovScore(chess.engine.Cp(50), turn), **flags)
    engine, _ = service(result)
    assert engine.evaluate(INITIAL).score.bound == expected


@pytest.mark.parametrize('change', [
    {'best_move': None}, {'best_move': chess.Move.from_uci('e2e5')},
    {'info': {}}, {'info': {'score': chess.engine.PovScore(chess.engine.Mate(0), chess.WHITE)}},
    {'info': {'score': chess.engine.PovScore(chess.engine.Cp(1), chess.WHITE), 'depth': 21}},
    {'info': {'score': chess.engine.PovScore(chess.engine.Cp(1), chess.WHITE), 'depth': True}},
    {'info': {'score': chess.engine.PovScore(chess.engine.Cp(1), chess.WHITE), 'lowerbound': True, 'upperbound': True}},
])
def test_bad_engine_result_rejected_and_lock_released(change):
    engine, _ = service(replace(raw(), **change))
    with pytest.raises(sf.StockfishError, match='STOCKFISH_PROTOCOL_ERROR'):
        engine.evaluate(INITIAL)
    assert engine.gate.lock.acquire(blocking=False)
    engine.gate.lock.release()


@pytest.mark.parametrize('code,status', [('STOCKFISH_NOT_FOUND',503), ('STOCKFISH_UNAVAILABLE',503),
                                        ('STOCKFISH_TIMEOUT',504), ('STOCKFISH_PROTOCOL_ERROR',502),
                                        ('STOCKFISH_BUSY',503), ('STOCKFISH_CLEANUP_FAILED',503)])
def test_http_typed_error_without_sensitive_path(monkeypatch, code, status):
    monkeypatch.setenv('STOCKFISH_ENABLED','true')
    async def runner(*args):
        raise sf.StockfishError(code,status)
    with TestClient(create_app(stockfish_runner=runner)) as client:
        response = client.get('/api/v1/evaluate/'+quote(INITIAL,safe=''))
    assert response.status_code == status and response.json() == {'detail': {'code': code}}


@pytest.mark.parametrize('safe',['','/'])
def test_http_routes_encoded_slashes_and_existing_endpoints(monkeypatch, safe):
    monkeypatch.setenv('STOCKFISH_ENABLED','true')
    async def runner(settings, board, gate):
        return raw(board)
    with TestClient(create_app(stockfish_runner=runner)) as client:
        assert client.get('/api/v1/healthcheck').status_code == 200
        assert client.post('/api/v1/positions/validate',json={'fen':INITIAL}).status_code == 200
        response = client.get('/api/v1/evaluate/'+quote(INITIAL,safe=safe))
        assert response.status_code == 200
        data = response.json()
        assert data['source_mode'] == 'local_engine' and data['source'] == 'stockfish'
        assert data['score']['perspective'] == 'white' and data['position']['repetition_status']=='unknown_without_history'
        schema = client.get('/openapi.json').json()
        assert '/api/v1/evaluate/{fen}' in schema['paths']
        assert client.get('/api/v1/evaluate/'+quote(quote(INITIAL,safe=''),safe='')).status_code == 422


def test_startup_health_invalid_and_terminal_never_spawn(monkeypatch):
    monkeypatch.setenv('STOCKFISH_ENABLED','true')
    with TestClient(create_app()) as client:
        assert client.get('/api/v1/healthcheck').json() == {'status':'ok'}
        assert client.get('/api/v1/evaluate/bad').status_code == 422
        data=client.get('/api/v1/evaluate/'+quote('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',safe='')).json()
        assert data['status']=='terminal' and data['score'] is None


def test_concurrent_request_rejected_no_queue_and_global_gate():
    entered, release = Event(), Event()
    async def runner(settings, board, gate):
        entered.set()
        assert release.wait(timeout=3)
        return raw(board)
    first = sf.StockfishService(StockfishSettings(True),runner=runner)
    second, calls = service()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(first.evaluate,INITIAL)
        assert entered.wait(timeout=3)
        try:
            with pytest.raises(sf.StockfishError,match='STOCKFISH_BUSY'):
                second.evaluate(INITIAL)
            assert not calls
        finally:
            release.set()
        assert result.result(timeout=3).status=='ok'
    assert second.evaluate(INITIAL).status=='ok'


@pytest.mark.parametrize('key,value,code', [
    ('STOCKFISH_ENABLED','yes','INVALID_STOCKFISH_ENABLED'),
    ('STOCKFISH_TIME_SECONDS','nan','INVALID_STOCKFISH_TIME_SECONDS'),
    ('STOCKFISH_TIME_SECONDS','inf','INVALID_STOCKFISH_TIME_SECONDS'),
    ('STOCKFISH_TIME_SECONDS','2','INVALID_STOCKFISH_TIME_SECONDS'),
    ('STOCKFISH_TIME_SECONDS','0','INVALID_STOCKFISH_TIME_SECONDS'),
    ('STOCKFISH_TIME_SECONDS','bad','INVALID_STOCKFISH_TIME_SECONDS'),
    ('STOCKFISH_PATH','relative; command','INVALID_STOCKFISH_PATH'),
    ('STOCKFISH_PATH','/private\npath','INVALID_STOCKFISH_PATH'),
])
def test_config_limits_and_safe_errors(monkeypatch,key,value,code):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError,match='^'+code+'$'):
        Settings.from_env()


class FakeTransport:
    def __init__(self):
        self.returncode = None
        self.closed = False
        self.killed = False
        self.finished = asyncio.get_running_loop().create_future()

    def get_returncode(self):
        return self.returncode

    def exit(self,code):
        self.returncode = code
        if not self.finished.done():
            self.finished.set_result(code)

    def kill(self):
        self.killed = True
        self.exit(-9)

    def close(self):
        self.closed = True
        if self.returncode is None:
            self.kill()


class FakeAnalysis:
    def __init__(self,updates,move):
        self.updates=iter(updates)
        self.move=move
        self.stopped=False

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.stopped=True

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.updates)
        except StopIteration:
            raise StopAsyncIteration

    async def wait(self):
        return chess.engine.BestMove(self.move,None)


class FakeProtocol:
    def __init__(self,transport):
        self.returncode=transport.finished
        self.transport=transport
        self.id={'name':'Stockfish simulated'}
        self.output_exceeded=False
        self.options_seen=None
        self.limit_seen=None
        self.quit_seen=False
        self.analysis_result=FakeAnalysis([
            {'score':chess.engine.PovScore(chess.engine.Cp(60),chess.WHITE),'lowerbound':True},
            {'score':chess.engine.PovScore(chess.engine.Cp(40),chess.WHITE),'depth':9},
        ],chess.Move.from_uci('e2e4'))

    async def initialize(self):
        pass

    async def configure(self,options):
        self.options_seen=options

    async def analysis(self,board,limit,**kwargs):
        self.limit_seen=limit
        assert kwargs['multipv']==1 and not (kwargs['info'] & chess.engine.INFO_PV)
        return self.analysis_result

    async def quit(self):
        self.quit_seen=True
        self.transport.exit(0)


async def indefinitely(*args,**kwargs):
    await asyncio.Future()


@pytest.fixture
def fake_process(monkeypatch):
    objects=[]
    async def spawn(path):
        transport=FakeTransport()
        protocol=FakeProtocol(transport)
        objects.append((transport,protocol))
        return transport,protocol
    monkeypatch.setattr(sf,'spawn_engine',spawn)
    return objects,spawn


def test_uci_lifecycle_options_bounds_reset_and_reaped(fake_process):
    objects,_=fake_process
    engine=sf.StockfishService(StockfishSettings(True))
    result=engine.evaluate(INITIAL)
    transport,protocol=objects[0]
    assert result.score.value==40 and result.score.bound=='none' and result.depth==9
    assert protocol.options_seen=={'Threads':1,'Hash':16}
    assert protocol.limit_seen.time==0.5 and protocol.limit_seen.depth==20
    assert protocol.quit_seen and transport.closed and transport.returncode==0 and not transport.killed
    assert protocol.analysis_result.stopped and not engine.gate.quarantined


@pytest.mark.parametrize('phase',['initialize','analysis'])
def test_timeout_kills_process_and_allows_next_request(fake_process,monkeypatch,phase):
    objects,original=fake_process
    async def spawn(path):
        transport,protocol=await original(path)
        setattr(protocol,phase,indefinitely)
        protocol.quit=indefinitely
        return transport,protocol
    monkeypatch.setattr(sf,'spawn_engine',spawn)
    monkeypatch.setattr(sf,'STARTUP_TIMEOUT',0.01)
    monkeypatch.setattr(sf,'ANALYSIS_TIMEOUT',0.01)
    monkeypatch.setattr(sf,'QUIT_TIMEOUT',0.01)
    engine=sf.StockfishService(StockfishSettings(True))
    with pytest.raises(sf.StockfishError,match='STOCKFISH_TIMEOUT') as error:
        engine.evaluate(INITIAL)
    assert error.value.http_status==504
    assert objects[0][0].killed and objects[0][0].closed and not engine.gate.quarantined
    monkeypatch.setattr(sf,'spawn_engine',original)
    assert engine.evaluate(INITIAL).status=='ok'


@pytest.mark.parametrize('error,code,status', [
    (FileNotFoundError('/private/path'),'STOCKFISH_NOT_FOUND',503),
    (PermissionError('/private/path'),'STOCKFISH_UNAVAILABLE',503),
    (chess.engine.EngineTerminatedError('/private/path'),'STOCKFISH_UNAVAILABLE',503),
    (chess.engine.EngineError('/private/path'),'STOCKFISH_PROTOCOL_ERROR',502),
])
def test_spawn_errors_sanitized(monkeypatch,error,code,status):
    async def spawn(path):
        raise error
    monkeypatch.setattr(sf,'spawn_engine',spawn)
    with pytest.raises(sf.StockfishError,match='^'+code+'$') as result:
        sf.StockfishService(StockfishSettings(True)).evaluate(INITIAL)
    assert result.value.http_status==status and '/private' not in str(result.value)


def test_cleanup_failure_quarantines_worker(fake_process,monkeypatch):
    objects,original=fake_process
    async def spawn(path):
        transport,protocol=await original(path)
        protocol.quit=indefinitely
        transport.kill=lambda: None
        transport.close=lambda: None
        return transport,protocol
    monkeypatch.setattr(sf,'spawn_engine',spawn)
    monkeypatch.setattr(sf,'QUIT_TIMEOUT',0.01)
    monkeypatch.setattr(sf,'KILL_WAIT_TIMEOUT',0.01)
    engine=sf.StockfishService(StockfishSettings(True))
    with pytest.raises(sf.StockfishError,match='STOCKFISH_CLEANUP_FAILED'):
        engine.evaluate(INITIAL)
    assert engine.gate.quarantined
    with pytest.raises(sf.StockfishError,match='STOCKFISH_UNAVAILABLE'):
        engine.evaluate(INITIAL)
    assert len(objects)==1


@pytest.mark.parametrize('content',[b'x'*(sf.MAX_UCI_LINE+1), b'info\n'*(sf.MAX_UCI_BYTES//5+1)])
def test_uci_output_bounded_before_parser(content):
    async def check():
        protocol=sf.BoundedUciProtocol()
        transport=FakeTransport()
        protocol.connection_made(transport)
        protocol.pipe_data_received(1,content)
        assert protocol.output_exceeded and transport.closed and not protocol.buffer[1]
    asyncio.run(check())


def test_spawn_argv_is_not_shell_and_does_not_inherit_secret(monkeypatch):
    seen=[]
    monkeypatch.setenv('LICHESS_API_TOKEN','simulated-private-token')
    async def popen(*args,**kwargs):
        seen.append((args,kwargs))
        return None,None
    monkeypatch.setattr(sf.BoundedUciProtocol,'popen',popen)
    asyncio.run(SPAWN_FACTORY('/path/engine with spaces;literal'))
    args,kwargs=seen[0]
    assert args==(['/path/engine with spaces;literal'],)
    assert 'shell' not in kwargs and 'LICHESS_API_TOKEN' not in kwargs['env']
    assert kwargs['stderr'] == sf.subprocess.DEVNULL
