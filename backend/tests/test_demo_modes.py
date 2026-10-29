"""Régressions simulées : aucun fournisseur ni processus moteur n'est exécuté."""
from dataclasses import replace
from unittest.mock import Mock
import chess
import chess.engine
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.demo import BoundedExplorer, DemoSettings
from app.explorer import ExplorerError, OpeningExplorer
from app.game import snapshot
from app.stockfish import RawEvaluation, StockfishError


@pytest.fixture(autouse=True)
def closed(monkeypatch):
    for k, v in dict(DEMO_ENABLED='false', DEMO_ALLOW_LIVE='false', EXPLORER_MODE='disabled',
        EXPLORER_DEFAULT_MODE='disabled', STOCKFISH_ENABLED='false', ANALYSIS_DEFAULT_ENGINE='false',
        GAME_ALLOW_TOOLS='false', YOUTUBE_MODE='disabled').items(): monkeypatch.setenv(k,v)


def setup(monkeypatch, live=False, handler=None, runner=None):
    monkeypatch.setenv('DEMO_ENABLED','true')
    if live:
        for k in ('DEMO_ALLOW_LIVE','STOCKFISH_ENABLED','GAME_ALLOW_TOOLS'):monkeypatch.setenv(k,'true')
        monkeypatch.setenv('EXPLORER_MODE','live')
        def client(_):return httpx.Client(transport=httpx.MockTransport(handler or payload))
        monkeypatch.setattr('app.main.live_client',client)
    app=create_app(stockfish_runner=runner or fake_engine)
    return app,TestClient(app,client=('127.0.0.1',50000))


def payload(request):
    b=chess.Board(request.url.params['fen']);moves=sorted(b.legal_moves,key=lambda m:m.uci())[:2]
    return httpx.Response(200,json={'white':6,'draws':2,'black':2,'moves':[
        {'uci':m.uci(),'san':b.san(m),'white':6+i,'draws':2,'black':2} for i,m in enumerate(moves)]})


async def fake_engine(settings,board,gate):
    return RawEvaluation({'score':chess.engine.PovScore(chess.engine.Cp(42),chess.WHITE),'depth':8},
                         sorted(board.legal_moves,key=lambda m:m.uci())[0],'Stockfish test')


def body(history=None,mode='simulation'):
    history=history or [];b=chess.Board()
    for m in history:b.push_uci(m)
    return dict(demo_mode=mode,history=history,revision=len(history),snapshot=snapshot(history),fen=b.fen(en_passant='fen'))


def turn_request(history=None,mode='simulation',**kw):
    d=body(history,mode);d.pop('fen');return {**d,'mode':'computer','human_color':'white','move':'e2e4',**kw}


def test_closed_capabilities_hide_demo_and_routes_refuse():
    with TestClient(create_app(),client=('127.0.0.1',5)) as c:
        caps=c.get('/api/v1/demo/capabilities').json()
        assert not caps['demo_enabled'] and caps['allowed_modes']==[]
        for route,b in [('analysis',body()),('turn',turn_request())]:
            r=c.post('/api/v1/demo/'+route,json=b)
            assert r.status_code==403 and r.json()['detail']['code']=='DEMO_DISABLED'


@pytest.mark.parametrize('host',['192.168.0.5','172.18.0.1','testclient'])
def test_nonlocal_peer_cannot_use_host_or_forwarded_headers_as_auth(monkeypatch,host):
    app,_=setup(monkeypatch)
    with TestClient(app,client=(host,5)) as c:
        r=c.get('/api/v1/demo/capabilities',headers={'Host':'localhost','X-Forwarded-For':'127.0.0.1'})
        assert r.status_code==403


def test_foreign_origin_rejected_even_with_loopback_peer(monkeypatch):
    _,c=setup(monkeypatch)
    with c:assert c.get('/api/v1/demo/capabilities',headers={'Origin':'https://evil.invalid'}).status_code==403


@pytest.mark.parametrize('name',['DEMO_ENABLED','DEMO_ALLOW_LIVE'])
def test_invalid_boolean_fails_closed(monkeypatch,name):
    monkeypatch.setenv(name,'yes')
    with pytest.raises(ValueError,match='INVALID_'):create_app()


def test_live_requires_demo_at_startup(monkeypatch):
    monkeypatch.setenv('DEMO_ALLOW_LIVE','true')
    with pytest.raises(ValueError,match='DEMO_LIVE_REQUIRES_DEMO'):create_app()


def test_simulation_default_fixture_stats_score_and_sources(monkeypatch):
    app,c=setup(monkeypatch)
    app.state.stockfish.evaluate=Mock(side_effect=AssertionError('REAL_ENGINE_FORBIDDEN'))
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('REAL_EXPLORER_FORBIDDEN'))
    with c:
        assert c.get('/api/v1/demo/capabilities').json()['allowed_modes']==['simulation']
        r=c.post('/api/v1/demo/analysis',json=body());d=r.json()
        assert r.status_code==200 and d['simulation'] and d['demo_mode']=='simulation'
        assert d['data']['tools']['explorer']['result']['moves'][0]['statistics']['games']==10
        assert d['data']['tools']['engine']['result']['score']['value']==35
        assert all(p['source_mode']=='synthetic_fixture' for p in d['data']['provenance'] if p['tool']!='position')
        assert d['data']['tools']['engine']['result']['source_mode']=='synthetic_fixture'
        assert d['data']['graph']['framework']=='langgraph'
        r=c.post('/api/v1/demo/turn',json=turn_request()).json()
        assert r['data']['state']['history']==['e2e4','c7c5'] and r['data']['choice']['synthetic']
    app.state.stockfish.evaluate.assert_not_called();app.state.demo.live_explorer.moves.assert_not_called()


def test_unknown_fixture_position_is_empty_not_invented(monkeypatch):
    _,c=setup(monkeypatch)
    with c:
        d=c.post('/api/v1/demo/analysis',json=body(['a2a3'])).json()['data']
        assert d['status']=='partial' and d['tools']['explorer']['status']=='error'
        assert d['tools']['explorer']['result'] is None
        assert d['tools']['engine']['result'] is None
        assert d['errors'][0]['code']=='SIMULATION_NO_POSITION_DATA'


@pytest.mark.parametrize('missing',['DEMO_ALLOW_LIVE','STOCKFISH_ENABLED','GAME_ALLOW_TOOLS','EXPLORER_MODE'])
def test_every_server_ceiling_required_even_for_forged_client(monkeypatch,missing):
    app,c=setup(monkeypatch,live=True)
    monkeypatch.setenv(missing,'disabled' if missing=='EXPLORER_MODE' else 'false')
    app=create_app(stockfish_runner=fake_engine)
    with TestClient(app,client=('127.0.0.1',5)) as c:
        caps=c.get('/api/v1/demo/capabilities').json()
        if missing=='DEMO_ALLOW_LIVE':
            assert 'live' not in caps['allowed_modes']
            assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==403
            assert c.post('/api/v1/demo/turn',json=turn_request(mode='live')).status_code==403
        else:
            assert 'live' in caps['allowed_modes']
            r=c.post('/api/v1/demo/analysis',json=body(mode='live'))
            assert r.status_code==200
            if missing=='STOCKFISH_ENABLED':assert r.json()['data']['tools']['engine']['status']=='disabled'
            if missing=='EXPLORER_MODE':assert r.json()['data']['tools']['explorer']['status']=='disabled'
            t=c.post('/api/v1/demo/turn',json=turn_request(mode='live'))
            assert t.status_code==200 and not t.json()['data']['choice']['synthetic']
            if missing=='GAME_ALLOW_TOOLS':assert t.json()['data']['status']=='unavailable'



@pytest.mark.parametrize('update',[{'fen':chess.STARTING_FEN.replace('0 1','1 1')},{'snapshot':'a'*64},{'revision':1}])
def test_fen_snapshot_revision_checked_before_tools(monkeypatch,update):
    app,c=setup(monkeypatch,live=True)
    app.state.demo.live_graph.invoke=Mock(side_effect=AssertionError('UNTRUSTED_POSITION'))
    with c:assert c.post('/api/v1/demo/analysis',json={**body(mode='live'),**update}).status_code==409
    app.state.demo.live_graph.invoke.assert_not_called()


@pytest.mark.parametrize('route,change',[('turn',{'source':'engine'}),('analysis',{'include_engine':False}),('analysis',{'demo_mode':'other'})])
def test_client_cannot_select_partial_or_conflicting_policy(monkeypatch,route,change):
    _,c=setup(monkeypatch)
    with c:
        r=c.post('/api/v1/demo/'+route,json={**(turn_request() if route=='turn' else body()),**change})
        assert r.status_code==422 and 'fen' not in r.text and 'input' not in r.text


def test_live_real_route_uses_mock_masters_most_frequent_and_engine_analysis(monkeypatch):
    calls=[]
    def handler(r):calls.append(r);return payload(r)
    app,c=setup(monkeypatch,live=True,handler=handler)
    with c:
        r=c.post('/api/v1/demo/turn',json=turn_request(mode='live'));d=r.json()
        assert r.status_code==200 and not d['simulation']
        assert d['data']['choice']['source']=='lichess_opening_explorer'
        assert d['data']['choice']['source_mode']=='live' and not d['data']['choice']['synthetic']
        # Choisit le deuxième candidat (fréquence 11 vs 10), pas un tri UCI.
        assert d['data']['state']['history'][-1]=='a7a6'
        r=c.post('/api/v1/demo/analysis',json=body(d['data']['state']['history'],'live')).json()
        assert r['data']['tools']['engine']['result']['score']['value']==42
        assert r['data']['tools']['explorer']['result']['source_mode']=='live'
    assert len(calls)==2


def test_no_theory_falls_to_engine_never_to_fixture(monkeypatch):
    _,c=setup(monkeypatch,live=True,handler=lambda r:httpx.Response(200,json={'moves':[]}))
    with c:
        d=c.post('/api/v1/demo/turn',json=turn_request(mode='live')).json()['data']
        assert d['choice']['source']=='stockfish' and not d['choice']['synthetic']
        assert d['state']['history']==['e2e4','a7a5']


def test_429_no_retry_respects_retry_after_across_fens_and_keeps_engine(monkeypatch):
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(429,headers={'Retry-After':'90'},text='sensitive-upstream-body')
    app,c=setup(monkeypatch,live=True,handler=handler)
    tick=[1000.0];app.state.demo.clock=lambda:tick[0];app.state.demo.live_explorer.clock=lambda:tick[0]
    with c:
        d=c.post('/api/v1/demo/analysis',json=body(mode='live')).json()['data']
        assert d['status']=='partial' and d['tools']['engine']['result']
        assert d['errors'][0]['retry_after_seconds']==90
        tick[0]+=3
        d=c.post('/api/v1/demo/analysis',json=body(['e2e4'],'live')).json()['data']
        assert d['status']=='partial' and d['tools']['explorer']['result'] is None
        assert len(calls)==1 and 'sensitive' not in str(d)


def test_missing_stockfish_and_upstream_unavailable_keep_human_move(monkeypatch):
    async def absent(*args):raise StockfishError('STOCKFISH_NOT_FOUND',503)
    _,c=setup(monkeypatch,live=True,handler=lambda r:httpx.Response(503),runner=absent)
    with c:
        r=c.post('/api/v1/demo/turn',json=turn_request(mode='live'));d=r.json()['data']
        assert r.status_code==200 and d['status']=='unavailable'
        assert d['state']['history']==['e2e4'] and not d['choice']['synthetic']
        assert 'STOCKFISH_NOT_FOUND' in d['errors']


def test_injected_transport_never_claimed_as_authentic(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    app.state.demo.live_explorer.delegate=OpeningExplorer(httpx.Client(transport=httpx.MockTransport(payload)),'injected_transport')
    with c:
        d=c.post('/api/v1/demo/analysis',json=body(mode='live')).json()['data']
        assert d['status']=='partial' and d['errors'][0]['code']=='DEMO_AUTHENTIC_SOURCE_REQUIRED'


def test_busy_and_rate_limited_no_provider_invocation(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    graph=Mock(wraps=app.state.demo.live_graph.invoke);app.state.demo.live_graph.invoke=graph
    with c:
        app.state.demo.gate.acquire()
        try:assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==503
        finally:app.state.demo.gate.release()
        graph.assert_not_called()
        assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==200
        assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==429
        assert graph.call_count==1


def test_hourly_budget_refuses_before_provider(monkeypatch):
    app,c=setup(monkeypatch,live=True);app.state.demo.live_count=120
    app.state.demo.live_graph.invoke=Mock(side_effect=AssertionError('BUDGET'))
    with c:assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==429
    app.state.demo.live_graph.invoke.assert_not_called()


def test_cache_same_fen_no_extra_upstream(monkeypatch):
    calls=[]
    def handler(r):calls.append(r);return payload(r)
    app,c=setup(monkeypatch,live=True,handler=handler)
    tick=[1000.0];app.state.demo.clock=lambda:tick[0];app.state.demo.live_explorer.clock=lambda:tick[0]
    with c:
        for _ in range(2):
            assert c.post('/api/v1/demo/analysis',json=body(mode='live')).status_code==200
            tick[0]+=3
    assert len(calls)==1


@pytest.mark.parametrize('human_color,history,move,plies',[
    ('white',[],'e2e4',2),('black',[],None,1),('black',['e2e4'],'c7c5',3)])
def test_simulation_computer_both_camps(monkeypatch,human_color,history,move,plies):
    _,c=setup(monkeypatch)
    with c:
        d=c.post('/api/v1/demo/turn',json=turn_request(history,human_color=human_color,move=move)).json()['data']
        assert d['state']['revision']==plies and d['choice']['synthetic']


def test_study_never_chooses_opponent_and_limit_24_preserved(monkeypatch):
    app,c=setup(monkeypatch)
    app.state.demo.sim_game.choose=Mock(side_effect=AssertionError('NO_OPPONENT_IN_STUDY'))
    with c:
        d=c.post('/api/v1/demo/turn',json=turn_request(mode='simulation',mode_unused='bad'))
        assert d.status_code==422
        req=turn_request();req['mode']='study'
        d=c.post('/api/v1/demo/turn',json=req).json()['data'];assert d['state']['revision']==1
    app.state.demo.sim_game.choose.assert_not_called()


def test_capabilities_no_sensitive_values_or_probe(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    app.state.stockfish.evaluate=Mock(side_effect=AssertionError('NO_PROBE'))
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('NO_PROBE'))
    with c:
        r=c.get('/api/v1/demo/capabilities');assert r.status_code==200
        assert set(r.json()['allowed_modes'])=={'simulation','live'}
        assert 'token' not in r.text.lower() and '/usr/' not in r.text
    app.state.stockfish.evaluate.assert_not_called();app.state.demo.live_explorer.moves.assert_not_called()


def test_historical_engine_gate_is_respected_by_facade(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    app.state.stockfish.gate.lock.acquire()
    try:
        with c:
            d=c.post('/api/v1/demo/analysis',json=body(mode='live')).json()['data']
            assert d['status']=='partial' and d['tools']['explorer']['result']
            assert d['errors'][0]['code']=='STOCKFISH_BUSY'
            assert d['tools']['engine']['result'] is None
    finally:app.state.stockfish.gate.lock.release()


def test_terminal_position_no_automatic_tool_or_opponent(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    app.state.stockfish.evaluate=Mock(side_effect=AssertionError('TERMINAL_NO_ENGINE'))
    app.state.demo.live_explorer.moves=Mock(side_effect=AssertionError('TERMINAL_NO_MASTERS'))
    history=['f2f3','e7e5','g2g4','d8h4']
    with c:
        d=c.post('/api/v1/demo/analysis',json=body(history,'live')).json()['data']
        assert d['status']=='terminal' and d['tools']['engine']['status']=='skipped_terminal'
        d=c.post('/api/v1/demo/turn',json=turn_request(history,mode='live',move=None)).json()['data']
        assert d['status']=='terminal' and d['state']['history']==history
    app.state.stockfish.evaluate.assert_not_called();app.state.demo.live_explorer.moves.assert_not_called()


def test_fixture_engine_isolated_from_real_engine_quarantine(monkeypatch):
    app,c=setup(monkeypatch,live=True)
    app.state.stockfish.gate.lock.acquire()
    try:
        with c:
            d=c.post('/api/v1/demo/analysis',json=body()).json()['data']
            assert d['tools']['engine']['status']=='ok'
            assert d['tools']['engine']['result']['source_mode']=='synthetic_fixture'
    finally:app.state.stockfish.gate.lock.release()


def test_historical_evaluation_schema_not_widened(monkeypatch):
    app,_=setup(monkeypatch)
    schemas=app.openapi()['components']['schemas']
    assert schemas['EvaluationResponse']['properties']['source_mode']['const']=='local_engine'
    assert set(schemas['DemoEvaluation']['properties']['source_mode']['enum'])=={'local_engine','synthetic_fixture'}


def test_forwarded_header_refused_even_when_peer_loopback(monkeypatch):
    _,c=setup(monkeypatch)
    with c:
        r=c.get('/api/v1/demo/capabilities',headers={'X-Forwarded-For':'127.0.0.1'})
        assert r.status_code==403 and r.json()['detail']['code']=='DEMO_FORWARDED_NOT_ALLOWED'


def test_real_opponent_requires_actual_frequency_before_most_played_claim(monkeypatch):
    def no_counts(request):
        b=chess.Board(request.url.params['fen']);m=sorted(b.legal_moves,key=lambda m:m.uci())[0]
        return httpx.Response(200,json={'moves':[{'uci':m.uci(),'san':b.san(m)}]})
    _,c=setup(monkeypatch,live=True,handler=no_counts)
    with c:
        d=c.post('/api/v1/demo/turn',json=turn_request(mode='live')).json()['data']
        assert d['choice']['source']=='stockfish' and not d['choice']['synthetic']
        assert 'THEORY_EMPTY_OR_ILLEGAL' in d['errors']
