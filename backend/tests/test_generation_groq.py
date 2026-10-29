"""Groq contract doubles only. No actual key lookup or external request."""
import json
from dataclasses import replace
from unittest.mock import Mock
import httpx,pytest
from app.conversation_generators import Settings,HttpGenerator,GeneratorRouter,APPROVED_API
from app.conversation import ConversationService
from test_conversation import request
from test_generation_local import envelope,local_envelope,MODEL

MODEL_GROQ='openai/gpt-oss-120b'
KEY='SYNTHETIC_GROQ_CREDENTIAL'
SETTINGS=Settings(api_provider='groq',api_model=MODEL_GROQ,api_endpoint=APPROVED_API['groq'],api_secret_env='GROQ_API_KEY')
def invoke(handler,*,settings=SETTINGS,key=KEY,intent='position'):
    body=request([] if intent=='opening_theory' else ['e2e4','c7c5'],intent=intent,request_generation=False)
    e=ConversationService().ask(body).passages
    adapter=HttpGenerator('groq_api',settings,transport=httpx.MockTransport(handler),key_lookup=lambda name:key)
    return adapter.generate(body.question,body.fen,e,intent=intent),e

def success(scope='position'):
    e=ConversationService().ask(request([] if scope=='opening_theory' else ['e2e4','c7c5'],intent=scope,request_generation=False)).passages
    return envelope(e,scope,MODEL_GROQ)

@pytest.mark.parametrize('intent',['position','opening_theory'])
def test_groq_success_shared_prompt_and_contract_bounded_parameters(intent):
    calls=[]
    def handle(req):
        calls.append(req);assert str(req.url)==APPROVED_API['groq']
        assert req.headers['authorization']=='Bearer '+KEY
        payload=json.loads(req.content)
        assert payload['model']==MODEL_GROQ and payload['max_completion_tokens']==2048
        assert payload['reasoning_effort']=='low'
        assert payload['temperature']==0 and payload['stream'] is False
        assert payload['response_format']=={'type':'json_object'}
        assert not {'random_seed','seed','reasoning_format','max_tokens','cache_prompt'}&payload.keys()
        assert json.loads(payload['messages'][1]['content'])['intent']==intent
        return httpx.Response(200,json=success(intent))
    r,e=invoke(handle,intent=intent)
    assert r.status=='test_double' and r.provider=='groq_api' and r.engine=='Groq'
    assert r.actual_model==r.requested_model==r.model==MODEL_GROQ and r.answer.scope==intent
    assert r.answer.paragraphs[0].citation_ids==[e[0].chunk_id] and r.usage.total_tokens==340
    assert len(calls)==1 and KEY not in r.model_dump_json()

@pytest.mark.parametrize('status,reason',[(401,'GENERATOR_AUTH_UNAVAILABLE'),(403,'GENERATOR_AUTH_UNAVAILABLE'),(429,'PROVIDER_RATE_LIMITED'),(503,'PROVIDER_SERVER_ERROR'),(302,'GENERATOR_HTTP_ERROR')])
def test_groq_http_errors_no_retry_no_fallback_no_body_leak(status,reason):
    calls=[]
    def handle(req):calls.append(req);return httpx.Response(status,json={'error':KEY+' PRIVATE_PATH'},headers={'Location':'https://evil.example'})
    r,_=invoke(handle)
    assert r.status=='provider_unavailable' and r.reason==reason and len(calls)==1
    assert all(req.url.host=='api.groq.com' for req in calls)
    assert KEY not in r.model_dump_json() and 'PRIVATE_PATH' not in r.model_dump_json()


def test_groq_timeout_has_no_second_call():
    calls=[]
    def handle(req):calls.append(req);raise httpx.ReadTimeout('PRIVATE_TIMEOUT')
    r,_=invoke(handle)
    assert r.reason=='GENERATOR_TIMEOUT' and r.status=='provider_unavailable' and len(calls)==1
    assert 'PRIVATE_TIMEOUT' not in r.model_dump_json()

@pytest.mark.parametrize('key',['',None,'contains whitespace'])
def test_groq_missing_or_invalid_key_never_calls_transport(key):
    http=Mock(side_effect=AssertionError('NO_HTTP'));r,_=invoke(http,key=key)
    assert r.reason=='GROQ_KEY_UNAVAILABLE' and not r.executed;http.assert_not_called()

@pytest.mark.parametrize('change',[
    {'api_endpoint':'https://api.groq.com/openai/v1/chat/completions?extra=1'},
    {'api_endpoint':'https://evil.example'},
    {'api_secret_env':'MISTRAL_API_KEY'},
    {'api_secret_env':'GROQ_OTHER_KEY'},
    {'api_model':'openai/other'},
    {'api_model':'https://api.groq.com'},
    {'api_model':'../../private'},
    {'api_provider':'unknown'},
])
def test_groq_bad_configuration_rejected_before_key_or_http(change):
    key=Mock(side_effect=AssertionError('NO_KEY'));http=Mock(side_effect=AssertionError('NO_HTTP'))
    body=request();e=ConversationService().ask(body.model_copy(update={'request_generation':False})).passages
    r=HttpGenerator('groq_api',replace(SETTINGS,**change),key_lookup=key,transport=http).generate(body.question,body.fen,e)
    assert r.reason=='API_CONFIGURATION_REJECTED' and not r.executed;key.assert_not_called();http.assert_not_called()

@pytest.mark.parametrize('change,reason',[
    ({'model':'other/model'},'GENERATOR_ENVELOPE_INVALID'),
    ({'choices':[{'finish_reason':'length'}]},'GENERATION_OUTPUT_TRUNCATED'),
    ({'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':None,'reasoning':'PRIVATE_REASONING'}}]},'GENERATOR_ENVELOPE_INVALID'),
    ({'usage':{'prompt_tokens':True,'completion_tokens':1,'total_tokens':2}},'GENERATOR_USAGE_INVALID'),
    ({'usage':{'prompt_tokens':2,'completion_tokens':1,'total_tokens':4}},'GENERATOR_USAGE_INVALID'),
])
def test_groq_bad_envelopes_never_salvaged(change,reason):
    raw=success();raw.update(change);r,_=invoke(lambda req:httpx.Response(200,json=raw))
    assert r.status=='abstain' and r.reason==reason and r.answer is None
    assert 'PRIVATE_REASONING' not in r.model_dump_json()

@pytest.mark.parametrize('output',[
    'PRIVATE_INVALID_JSON',
    {'scope':'position','paragraphs':[{'text':'Texte','citation_ids':['invented']}],'moves_uci':[]},
    {'scope':'opening_theory','abstain':True,'paragraphs':[],'moves_uci':[]},
    {'scope':'position','paragraphs':[{'text':'Texte','citation_ids':[]}],'moves_uci':['e2e5']},
])
def test_groq_output_validation_never_relaxed(output):
    raw=success();raw['choices'][0]['message']['content']=output if isinstance(output,str) else json.dumps(output)
    r,_=invoke(lambda req:httpx.Response(200,json=raw))
    assert r.reason=='GENERATION_OUTPUT_REJECTED' and r.answer is None
    assert 'PRIVATE_INVALID_JSON' not in r.model_dump_json()


def test_groq_model_abstention_and_reasoning_never_used_as_answer():
    raw=success();raw['choices'][0]['message'].update(reasoning='PRIVATE_REASONING',content=json.dumps({'scope':'position','abstain':True,'paragraphs':[],'moves_uci':[]}))
    r,_=invoke(lambda req:httpx.Response(200,json=raw))
    assert r.reason=='MODEL_ABSTAINED' and r.answer is None and 'PRIVATE_REASONING' not in r.model_dump_json()


def test_groq_credential_echo_is_rejected_before_returning_metadata():
    raw=success();raw['choices'][0]['message']['content']=KEY
    r,_=invoke(lambda req:httpx.Response(200,json=raw))
    assert r.reason=='GENERATOR_SENSITIVE_RESPONSE_REJECTED' and KEY not in r.model_dump_json()


def test_router_config_switch_keeps_simulation_and_retrieval_and_no_secret_at_start():
    settings=[replace(SETTINGS,local_url='http://advisor-local:8080')];calls=[];key=Mock(return_value=KEY)
    e=ConversationService().ask(request(request_generation=False)).passages
    def api(req):
        calls.append(req);return httpx.Response(200,json=envelope(e,model=MODEL_GROQ if req.url.host=='api.groq.com' else 'mistral-small-TEST'))
    def local(req):return httpx.Response(200,json={'data':[{'id':MODEL}]} if req.method=='GET' else local_envelope(e))
    router=GeneratorRouter(lambda:settings[0],api_transport=httpx.MockTransport(api),local_transport=httpx.MockTransport(local),key_lookup=key)
    key.assert_not_called();service=ConversationService(generator=router)
    a=service.ask(request(demo_mode='live'));assert a.generation.provider=='groq_api'
    b=service.ask(request(demo_mode='simulation'));assert b.generation.provider=='local_llm'
    settings[0]=Settings();c=service.ask(request(demo_mode='live'));assert c.generation.provider=='mistral_api'
    assert [p.chunk_id for p in a.passages]==[p.chunk_id for p in b.passages]==[p.chunk_id for p in c.passages]
    assert key.call_args_list[0].args==('GROQ_API_KEY',) and key.call_args_list[1].args==('MISTRAL_API_KEY',)
    assert [r.url.host for r in calls]==['api.groq.com','api.mistral.ai']


def test_default_settings_still_mistral_and_simulation_disabled_never_reads_groq():
    assert Settings().api_provider=='mistral' and Settings().api_model=='mistral-small-latest'
    key=Mock(side_effect=AssertionError('NO_KEY'));router=GeneratorRouter(lambda:SETTINGS,key_lookup=key)
    result=router.generate_context(request(request_generation=False,demo_mode='live'),request().fen,[])
    assert result.status=='generation_disabled';key.assert_not_called()


def test_browser_provider_and_secret_overrides_forbidden():
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app()) as client:
        for key in ('api_provider','api_model','api_secret_env','GROQ_API_KEY'):
            body=request().model_dump();body[key]='SYNTHETIC_VALUE'
            assert client.post('/api/v1/advisor/conversation',json=body).status_code==422


def test_groq_busy_is_identified_without_secret_or_http():
    key=Mock(side_effect=AssertionError('NO_KEY'));router=GeneratorRouter(lambda:SETTINGS,key_lookup=key);router.gate.acquire()
    try:r=router.generate_context(request(demo_mode='live'),request().fen,[])
    finally:router.gate.release()
    assert r.reason=='GENERATOR_BUSY' and r.provider=='groq_api' and r.engine=='Groq' and r.model==MODEL_GROQ
    key.assert_not_called()


def test_groq_from_env_selection_never_reads_secret(monkeypatch):
    for name,value in {'ADVISOR_API_PROVIDER':'groq','ADVISOR_API_MODEL':MODEL_GROQ,'ADVISOR_API_ENDPOINT':APPROVED_API['groq'],'ADVISOR_API_SECRET_ENV':'GROQ_API_KEY'}.items():monkeypatch.setenv(name,value)
    assert Settings.from_env()==SETTINGS


def test_groq_malformed_outer_json_is_sanitized():
    r,_=invoke(lambda req:httpx.Response(200,content=b'PRIVATE_MALFORMED'))
    assert r.reason=='GENERATOR_JSON_INVALID' and r.answer is None and 'PRIVATE_MALFORMED' not in r.model_dump_json()
