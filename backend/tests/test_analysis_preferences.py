"""Matrice serveur/défauts/HTTP, vrai LangGraph, aucun outil externe réel."""
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from pathlib import Path
from threading import Event
from urllib.parse import quote

import chess
import chess.engine
import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient

from app import cli
from app.analysis_preferences import PreferenceError, resolve_preferences
from app.config import Settings, StockfishSettings
from app.explorer_live import SecretConfigurationError, configured_live_client
from app.main import create_app
from app.stockfish import RawEvaluation, StockfishError

MODES = ['disabled','synthetic_fixture','live']
ALLOWED = {'disabled':{'disabled'}, 'synthetic_fixture':{'disabled','synthetic_fixture'}, 'live':set(MODES)}
INITIAL = chess.STARTING_FEN
TERMINAL = '7k/6Q1/6K1/8/8/8/8/8 b - - 0 1'


@pytest.mark.parametrize('ceiling,default,override', list(product(MODES,MODES,[None,*MODES])))
def test_complete_explorer_matrix(ceiling,default,override):
    if default not in ALLOWED[ceiling]:
        with pytest.raises(ValueError,match='EXPLORER_DEFAULT_MODE_NOT_ALLOWED'):
            Settings('matrix',explorer_mode=ceiling,explorer_default_mode=default)
        return
    settings = Settings('matrix',explorer_mode=ceiling,explorer_default_mode=default)
    effective = default if override is None else override
    if effective not in ALLOWED[ceiling]:
        with pytest.raises(PreferenceError,match='EXPLORER_MODE_NOT_ALLOWED'):
            resolve_preferences(settings,explorer_mode=override)
    else:
        result = resolve_preferences(settings,explorer_mode=override)
        assert result.explorer.resolved == effective
        assert result.explorer.ceiling == ceiling and result.explorer.default == default
        assert result.explorer.requested == override
        assert result.explorer.origin == ('default' if override is None else 'http')


@pytest.mark.parametrize('enabled,default,override', list(product([False,True],[False,True],[None,False,True])))
def test_complete_engine_matrix(enabled,default,override):
    if default and not enabled:
        with pytest.raises(ValueError,match='ANALYSIS_DEFAULT_ENGINE_NOT_ALLOWED'):
            Settings('matrix',stockfish=StockfishSettings(enabled),analysis_default_engine=default)
        return
    settings=Settings('matrix',stockfish=StockfishSettings(enabled),analysis_default_engine=default)
    effective=default if override is None else override
    if effective and not enabled:
        with pytest.raises(PreferenceError,match='ENGINE_NOT_ALLOWED'):
            resolve_preferences(settings,include_engine=override)
    else:
        result=resolve_preferences(settings,include_engine=override)
        assert result.engine.resolved == effective and result.engine.requested == override
        assert result.engine.origin == ('default' if override is None else 'http')


@pytest.mark.parametrize('ceiling,default,legacy', [
    (c,d,v) for c in MODES for d in ALLOWED[c] for v in (None,False,True)])
def test_legacy_single_resolution(ceiling,default,legacy):
    settings=Settings('legacy',explorer_mode=ceiling,explorer_default_mode=default)
    if legacy and ceiling=='disabled':
        with pytest.raises(PreferenceError,match='EXPLORER_MODE_NOT_ALLOWED'):
            resolve_preferences(settings,include_explorer=legacy)
        return
    expected = default if legacy is None else 'disabled' if not legacy else default if default!='disabled' else ceiling
    resolved=resolve_preferences(settings,include_explorer=legacy)
    assert resolved.explorer.resolved == expected
    assert resolved.explorer.origin == ('default' if legacy is None else 'legacy')


@pytest.mark.parametrize('legacy,mode', list(product([False,True],MODES)))
def test_legacy_and_new_mode_conflicts_and_consistent_pairs(legacy,mode):
    settings=Settings('legacy',explorer_mode='live')
    if legacy != (mode!='disabled'):
        with pytest.raises(PreferenceError,match='CONFLICTING_EXPLORER_PREFERENCES'):
            resolve_preferences(settings,include_explorer=legacy,explorer_mode=mode)
    else:
        result=resolve_preferences(settings,include_explorer=legacy,explorer_mode=mode)
        assert result.explorer.resolved==mode and result.explorer.origin=='http'


@pytest.mark.parametrize('variable,value,code',[
    ('EXPLORER_DEFAULT_MODE','on','INVALID_EXPLORER_DEFAULT_MODE'),
    ('EXPLORER_DEFAULT_MODE','','INVALID_EXPLORER_DEFAULT_MODE'),
    ('EXPLORER_DEFAULT_MODE','live','EXPLORER_DEFAULT_MODE_NOT_ALLOWED'),
    ('ANALYSIS_DEFAULT_ENGINE','on','INVALID_ANALYSIS_DEFAULT_ENGINE'),
    ('ANALYSIS_DEFAULT_ENGINE','','INVALID_ANALYSIS_DEFAULT_ENGINE'),
    ('ANALYSIS_DEFAULT_ENGINE','true','ANALYSIS_DEFAULT_ENGINE_NOT_ALLOWED'),
])
def test_invalid_startup_configuration_precedes_client_creation(variable,value,code,monkeypatch):
    monkeypatch.setenv(variable,value)
    monkeypatch.setattr('app.main.live_client',lambda _:pytest.fail('No client on invalid configuration'))
    with pytest.raises(ValueError,match=code):create_app()


@pytest.mark.parametrize('body,code',[
    ({'explorer_mode':'live'},'EXPLORER_MODE_NOT_ALLOWED'),
    ({'explorer_mode':'synthetic_fixture'},'EXPLORER_MODE_NOT_ALLOWED'),
    ({'include_explorer':True},'EXPLORER_MODE_NOT_ALLOWED'),
    ({'include_engine':True},'ENGINE_NOT_ALLOWED'),
    ({'explorer_mode':'disabled','include_explorer':True},'CONFLICTING_EXPLORER_PREFERENCES'),
    ({'explorer_mode':'live','include_explorer':False},'CONFLICTING_EXPLORER_PREFERENCES'),
])
@pytest.mark.parametrize('fen',[INITIAL,TERMINAL])
def test_http_refused_before_every_tool_even_if_terminal(body,code,fen,monkeypatch):
    app=create_app();calls=[]
    def unexpected(*args):calls.append('tool');raise AssertionError('Not allowed')
    monkeypatch.setattr(app.state.stockfish,'evaluate',unexpected)
    for explorer in app.state.explorers.values():monkeypatch.setattr(explorer,'moves',unexpected)
    with TestClient(app) as client:
        response=client.post('/api/v1/analysis/orchestrate',json={'fen':fen,**body})
        assert response.status_code==422 and response.json()['detail']['code']==code
    assert calls==[] and not app.state.orchestrator.gate.lock.locked()


@pytest.mark.parametrize('body',[
    {'explorer_mode':None},{'include_explorer':None},{'include_engine':None},
    {'explorer_mode':'on'},{'include_engine':'false'},{'include_explorer':0},
    {'stockfish_time_seconds':.1},{'stockfish_path':'/tmp/other'},
])
def test_http_invalid_fields_are_not_server_overrides(body):
    with TestClient(create_app()) as client:
        assert client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,**body}).status_code==422


def test_safe_upgrade_defaults_with_all_capabilities_enabled(monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','live');monkeypatch.setenv('STOCKFISH_ENABLED','true')
    monkeypatch.setattr('app.main.live_client',lambda _:(_ for _ in ()).throw(SecretConfigurationError('LICHESS_SECRET_UNREADABLE')))
    with TestClient(create_app()) as client:
        response=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL})
        assert response.status_code==200
        result=response.json()
        assert result['graph']['steps']==['validate_position','assemble_response']
        assert result['preferences']['explorer']['resolved']=='disabled'
        assert result['preferences']['engine']['resolved'] is False
        assert result['tools']['explorer']['status']==result['tools']['engine']['status']=='not_requested'


def test_live_ceiling_fixture_default_and_isolation_from_legacy(monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','live');monkeypatch.setenv('EXPLORER_DEFAULT_MODE','synthetic_fixture')
    requests=[]
    def transport(request):
        requests.append(request)
        return httpx.Response(200,json={'moves':[]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as live:
      app=create_app(live)
      with TestClient(app) as client:
        fixture=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL}).json()
        assert fixture['tools']['explorer']['result']['source_mode']=='synthetic_fixture'
        assert len(fixture['tools']['explorer']['result']['moves'])==2 and requests==[]
        off=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'disabled'}).json()
        assert off['tools']['explorer']['status']=='not_requested' and requests==[]
        selected=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'live'}).json()
        assert selected['tools']['explorer']['result']['source_mode']=='injected_transport' and len(requests)==1
        # GET conserve le mode du plafond historique, pas le défaut du graphe.
        legacy=client.get('/api/v1/moves/'+quote(INITIAL,safe='')).json()
        assert legacy['source_mode']=='injected_transport' and len(requests)==2
        again=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL}).json()
        assert again['tools']['explorer']['result']['source_mode']=='synthetic_fixture' and len(requests)==2
        assert again['graph']['steps']==['validate_position','fetch_explorer','assemble_response']
        assert app.state.explorer.source_mode=='injected_transport'
      assert app.state.explorers['synthetic_fixture'].client.is_closed and not live.is_closed


@pytest.mark.parametrize('status,code,http_status',[(401,'UPSTREAM_AUTHORIZATION_FAILED',502),
    (403,'UPSTREAM_AUTHORIZATION_FAILED',502),(429,'UPSTREAM_RATE_LIMITED',503)])
def test_authorized_real_adapter_failures_remain_partial(status,code,http_status,monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','live')
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(status,headers={'Retry-After':'3'}))) as live:
      with TestClient(create_app(live)) as client:
        response=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'live'})
        assert response.status_code==200 and response.json()['status']=='partial'
        assert response.json()['errors'][0]['code']==code
        assert response.json()['errors'][0]['http_status']==http_status
        assert response.json()['preferences']['explorer']['resolved']=='live'


def test_default_engine_and_explicit_false_or_true_use_injected_runner(monkeypatch):
    monkeypatch.setenv('STOCKFISH_ENABLED','true');monkeypatch.setenv('ANALYSIS_DEFAULT_ENGINE','true')
    seen=[]
    async def runner(settings,board,gate):
        seen.append(board.fen())
        return RawEvaluation({'score':chess.engine.PovScore(chess.engine.Cp(17),board.turn),'depth':5},
                             chess.Move.from_uci('e2e4'),'Stockfish simulated')
    with TestClient(create_app(stockfish_runner=runner)) as client:
        for choice,count in [({},1),({'include_engine':False},1),({'include_engine':True},2)]:
            response=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,**choice})
            assert response.status_code==200 and len(seen)==count
            result=response.json()
            assert result['preferences']['engine']['resolved'] is (choice.get('include_engine',True))
        terminal=client.post('/api/v1/analysis/orchestrate',json={'fen':TERMINAL}).json()
        assert terminal['status']=='terminal' and terminal['tools']['engine']['status']=='skipped_terminal'
        assert len(seen)==2


@pytest.mark.parametrize('failure',['LICHESS_SECRET_UNREADABLE','LICHESS_SECRET_INVALID'])
def test_unavailable_live_configuration_does_not_break_fixture_or_default(failure,monkeypatch,caplog):
    monkeypatch.setenv('EXPLORER_MODE','live');monkeypatch.setenv('EXPLORER_DEFAULT_MODE','synthetic_fixture')
    def broken(_):raise SecretConfigurationError(failure)
    monkeypatch.setattr('app.main.live_client',broken)
    with TestClient(create_app()) as client:
        assert client.get('/api/v1/healthcheck').status_code==200
        fixture=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL})
        assert fixture.json()['status']=='ok'
        live=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'live'})
        assert live.status_code==200 and live.json()['status']=='partial'
        assert live.json()['errors'][0]['code']==failure
        assert live.json()['tools']['explorer']['http_status']==503
        assert 'Authorization' not in live.text and '/run/secrets' not in live.text
        invalid=client.get('/api/v1/moves/bad')
        assert invalid.status_code==422
        terminal=client.get('/api/v1/moves/'+quote(TERMINAL,safe='')).json()
        assert terminal['status']=='terminal' and terminal['source_mode']=='live'
    assert failure not in caplog.text


def test_all_owned_clients_closed_and_injected_not_closed(monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','live');monkeypatch.setenv('LICHESS_API_TOKEN','simulated-only-token')
    owned=configured_live_client('unused',transport=httpx.MockTransport(lambda r:None))
    monkeypatch.setattr('app.main.live_client',lambda _:owned)
    app=create_app()
    with TestClient(app):
        assert not owned.is_closed and not app.state.explorers['synthetic_fixture'].client.is_closed
    assert owned.is_closed and app.state.explorers['synthetic_fixture'].client.is_closed


def test_interleaved_requests_never_mutate_live_adapter_or_inherit_other_mode(monkeypatch):
    monkeypatch.setenv('EXPLORER_MODE','live')
    started,release=Event(),Event();calls=[]
    def transport(request):
        calls.append('live');started.set()
        assert release.wait(3)
        return httpx.Response(200,json={'moves':[]})
    with httpx.Client(transport=httpx.MockTransport(transport)) as live:
      app=create_app(live)
      with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(client.post,'/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'live'})
        try:
            assert started.wait(3)
            # Le GET historique n'utilise pas le verrou du graphe ; ici on inspecte
            # le service synthétique séparé, sans mutation de l'objet live occupé.
            assert app.state.explorers['synthetic_fixture'].moves(INITIAL).source_mode=='synthetic_fixture'
            off=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'disabled'})
            assert off.json()['preferences']['explorer']['resolved']=='disabled'
            busy=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'synthetic_fixture'})
            assert busy.status_code==503 and busy.json()['detail']['code']=='ORCHESTRATION_BUSY'
        finally:release.set()
        assert future.result().status_code==200
        synthetic=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'synthetic_fixture'}).json()
        assert synthetic['tools']['explorer']['result']['source_mode']=='synthetic_fixture' and calls==['live']
        assert app.state.explorers['live'].client is live


@pytest.mark.parametrize('shell,expected_mode,expected_engine',[(False,'synthetic_fixture',True),(True,'disabled',False)])
def test_dotenv_new_preferences_and_shell_priority(tmp_path,monkeypatch,shell,expected_mode,expected_engine):
    path=tmp_path/'.env'
    path.write_text('EXPLORER_MODE=live\nEXPLORER_DEFAULT_MODE=synthetic_fixture\nSTOCKFISH_ENABLED=true\nANALYSIS_DEFAULT_ENGINE=true\n')
    # Enregistrer les clés dans monkeypatch avant la mutation directe dotenv.
    for key in ('EXPLORER_MODE','EXPLORER_DEFAULT_MODE','STOCKFISH_ENABLED','ANALYSIS_DEFAULT_ENGINE'):
        monkeypatch.setenv(key,'temporary');monkeypatch.delenv(key)
    if shell:
        monkeypatch.setenv('EXPLORER_DEFAULT_MODE','disabled');monkeypatch.setenv('ANALYSIS_DEFAULT_ENGINE','false')
    launched=[]
    def launch(*args,**kwargs):
        config=Settings.from_env();launched.append(config)
        assert config.explorer_default_mode==expected_mode and config.analysis_default_engine==expected_engine
    monkeypatch.setattr(cli.uvicorn,'run',launch)
    cli.main(['--env-file',str(path)])
    assert len(launched)==1


def test_synthetic_never_receives_live_bearer_and_owned_clients_both_close(monkeypatch,caplog):
    from app.explorer_fixtures import synthetic_transport
    monkeypatch.setenv('EXPLORER_MODE','live')
    monkeypatch.setenv('EXPLORER_DEFAULT_MODE','synthetic_fixture')
    monkeypatch.setenv('LICHESS_API_TOKEN','simulated-separated-bearer')
    seen=[]
    def live_transport(request):
        seen.append('live')
        assert request.headers['Authorization']=='Bearer simulated-separated-bearer'
        return httpx.Response(200,json={'moves':[]})
    def fixture_transport(request):
        seen.append('synthetic')
        assert 'Authorization' not in request.headers
        return synthetic_transport(request)
    live=configured_live_client('unused',transport=httpx.MockTransport(live_transport))
    monkeypatch.setattr('app.main.live_client',lambda _:live)
    monkeypatch.setattr('app.main.synthetic_transport',fixture_transport)
    app=create_app()
    with TestClient(app) as client:
        fixture=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL})
        actual=client.post('/api/v1/analysis/orchestrate',json={'fen':INITIAL,'explorer_mode':'live'})
        assert fixture.status_code==actual.status_code==200
        assert 'simulated-separated-bearer' not in fixture.text+actual.text+caplog.text
    assert seen==['synthetic','live']
    assert live.is_closed and app.state.explorers['synthetic_fixture'].client.is_closed
