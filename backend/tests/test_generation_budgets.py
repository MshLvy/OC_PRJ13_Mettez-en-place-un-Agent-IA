"""Output-budget migration and provider isolation; only synthetic transports."""
import json
from dataclasses import replace
from unittest.mock import Mock
import httpx,pytest
from app.conversation_generators import Settings,HttpGenerator,Failure
from test_generation_groq import SETTINGS as GROQ,KEY
from test_generation_local import evidence,envelope,local_envelope,MODEL
from test_conversation import request

PROVIDERS=('local_llm','mistral_api','groq_api')
def resolved(settings):return tuple(settings.output_budget(p) for p in PROVIDERS)

@pytest.mark.parametrize('changes,expected',[
    ({},(128,512,2048)),
    ({'GENERATION_MAX_TOKENS':''},(128,512,2048)),
    ({'GENERATION_MAX_TOKENS':'512'},(128,512,512)),
    ({'GENERATION_MAX_TOKENS':'64'},(64,64,64)),
    ({'GENERATION_MAX_TOKENS':'256'},(128,256,256)),
    ({'LOCAL_LLM_MAX_TOKENS':'64'},(64,512,2048)),
    ({'MISTRAL_MAX_TOKENS':'256'},(128,256,2048)),
    ({'GROQ_MAX_TOKENS':'1024'},(128,512,1024)),
    ({'GENERATION_MAX_TOKENS':'64','LOCAL_LLM_MAX_TOKENS':'128','MISTRAL_MAX_TOKENS':'512','GROQ_MAX_TOKENS':'2048'},(128,512,2048)),
    ({'GENERATION_MAX_TOKENS':'512','GROQ_MAX_TOKENS':'2048'},(128,512,2048)),
    ({'LOCAL_LLM_MAX_TOKENS':'','MISTRAL_MAX_TOKENS':'','GROQ_MAX_TOKENS':''},(128,512,2048)),
])
def test_env_priority_migration_and_independent_defaults(monkeypatch,changes,expected):
    for name,value in changes.items():monkeypatch.setenv(name,value)
    settings=Settings.from_env();assert resolved(settings)==expected
    assert settings.groq_reasoning_effort=='low'

@pytest.mark.parametrize('name,invalid',[
    ('LOCAL_LLM_MAX_TOKENS','129'),('LOCAL_LLM_MAX_TOKENS','63'),
    ('MISTRAL_MAX_TOKENS','513'),('MISTRAL_MAX_TOKENS','-1'),
    ('GROQ_MAX_TOKENS','2049'),('GROQ_MAX_TOKENS','0'),
    ('GROQ_MAX_TOKENS','2.5'),('GROQ_MAX_TOKENS','two'),('GROQ_MAX_TOKENS','2_048'),
    ('GENERATION_MAX_TOKENS','2048'),('GENERATION_MAX_TOKENS','garbage'),
    ('GROQ_REASONING_EFFORT','LOW'),('GROQ_REASONING_EFFORT','none'),('GROQ_REASONING_EFFORT',''),
])
def test_invalid_env_rejected_without_secret_or_http(monkeypatch,name,invalid):
    from app.conversation_generators import GeneratorRouter
    monkeypatch.setenv(name,invalid)
    key=Mock(side_effect=AssertionError('NO_KEY'));http=Mock(side_effect=AssertionError('NO_HTTP'))
    router=GeneratorRouter(key_lookup=key,api_transport=http,local_transport=http)
    for mode in ('live','simulation'):
        r=router.generate_context(request(demo_mode=mode),request().fen,evidence())
        assert (r.error_code or r.reason)=='GENERATION_CONFIGURATION_INVALID' and not r.executed
    key.assert_not_called();http.assert_not_called()

@pytest.mark.parametrize('changes',[
    {'local_max_tokens':True},{'local_max_tokens':129},{'mistral_max_tokens':513},
    {'groq_max_tokens':2049},{'groq_max_tokens':2048.0},{'max_tokens':513},
    {'groq_reasoning_effort':'unsupported'},
    # A malformed legacy value is never silently ignored, even when all specific overrides exist.
    {'max_tokens':-1,'local_max_tokens':128,'mistral_max_tokens':512,'groq_max_tokens':2048},
])
def test_invalid_direct_settings_never_read_key_or_send_http(changes):
    key=Mock(side_effect=AssertionError('NO_KEY'));http=Mock(side_effect=AssertionError('NO_HTTP'))
    for provider in PROVIDERS:
        settings=replace(GROQ,**changes) if provider=='groq_api' else Settings(local_url='http://advisor-local:8080',**changes)
        r=HttpGenerator(provider,settings,key_lookup=key,transport=http).generate('Pourquoi c5 ?',request().fen,evidence())
        assert (r.error_code or r.reason)=='GENERATION_CONFIGURATION_INVALID' and not r.executed
    key.assert_not_called();http.assert_not_called()

@pytest.mark.parametrize('provider,changes,expected',[
    ('local_llm',{},128),('mistral_api',{},512),('groq_api',{},2048),
    ('local_llm',{'local_max_tokens':64,'groq_max_tokens':2048},64),
    ('mistral_api',{'mistral_max_tokens':256,'groq_max_tokens':2048},256),
    ('groq_api',{'groq_max_tokens':1024,'mistral_max_tokens':64},1024),
    ('groq_api',{'max_tokens':512},512),
    ('groq_api',{'max_tokens':64,'groq_max_tokens':2048},2048),
])
def test_each_payload_uses_its_own_budget_and_only_its_parameters(provider,changes,expected):
    e=evidence();calls=[]
    settings=replace(GROQ,**changes) if provider=='groq_api' else Settings(local_url='http://advisor-local:8080',**changes)
    def handle(req):
        calls.append(req)
        if req.method=='GET':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        payload=json.loads(req.content)
        if provider=='groq_api':
            assert payload['max_completion_tokens']==expected and payload['reasoning_effort']=='low'
            assert not {'max_tokens','random_seed','seed','reasoning_format'}&payload.keys()
        else:
            assert payload['max_tokens']==expected and not {'reasoning_effort','max_completion_tokens'}&payload.keys()
            assert payload['seed' if provider=='local_llm' else 'random_seed']==0
            if provider=='local_llm':assert payload['cache_prompt'] and 'schema' in payload['response_format']
        return httpx.Response(200,json=local_envelope(e) if provider=='local_llm' else envelope(e,model='openai/gpt-oss-120b' if provider=='groq_api' else 'mistral-small-TEST'))
    key=Mock(return_value=KEY)
    r=HttpGenerator(provider,settings,key_lookup=key,transport=httpx.MockTransport(handle)).generate('Pourquoi c5 ?',request().fen,e)
    assert r.status=='test_double' and len(calls)==(2 if provider=='local_llm' else 1)
    if provider=='local_llm':key.assert_not_called()

@pytest.mark.parametrize('effort',['low','medium','high'])
def test_groq_reasoning_override_and_length_remains_strict(effort):
    calls=[];e=evidence()
    def handle(req):
        calls.append(req);assert json.loads(req.content)['reasoning_effort']==effort
        raw=envelope(e,model='openai/gpt-oss-120b');raw['choices'][0]['finish_reason']='length'
        return httpx.Response(200,json=raw)
    r=HttpGenerator('groq_api',replace(GROQ,groq_reasoning_effort=effort),key_lookup=lambda _:KEY,transport=httpx.MockTransport(handle)).generate('Pourquoi c5 ?',request().fen,e)
    assert r.reason=='GENERATION_OUTPUT_TRUNCATED' and r.answer is None and len(calls)==1
