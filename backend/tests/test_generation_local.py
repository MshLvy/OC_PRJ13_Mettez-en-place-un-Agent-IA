"""I09/B local OpenAI-compatible HTTP doubles, no GGUF or llama process."""
import json
from dataclasses import replace
from unittest.mock import Mock
import httpx,pytest
from app.conversation_generators import Settings,HttpGenerator,GeneratorRouter
from app.conversation import ConversationService
from test_conversation import request

MODEL='qwen2.5-1.5b-instruct-q4_k_m.gguf'
def evidence():return ConversationService().ask(request(request_generation=False)).passages

def envelope(e,scope='position',model=MODEL):
    return {'model':model,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps({'scope':scope,'abstain':False,'paragraphs':[{'text':'Le pion c5 contrôle d4.','citation_ids':[e[0].chunk_id]}],'moves_uci':[]})}}],'usage':{'prompt_tokens':300,'completion_tokens':40,'total_tokens':340}}

def local_envelope(e,scope='position',model=MODEL):
    result=envelope(e,scope,model)
    result['choices'][0]['message']['content']=json.dumps({'scope':scope,'text':'Le pion c5 contrôle d4.','cite':['S1']})
    return result

def test_local_discovers_actual_model_without_api_key_and_uses_shared_contract():
    e=evidence();calls=[];key=Mock(side_effect=AssertionError('NO_SECRET'))
    def handle(req):
        calls.append(req)
        assert req.url.host=='advisor-local' and 'authorization' not in req.headers
        if req.method=='GET':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        body=json.loads(req.content);assert body['model']==MODEL and body['max_tokens']==128 and body['stream'] is False
        return httpx.Response(200,json=local_envelope(e))
    r=HttpGenerator('local_llm',Settings(local_url='http://advisor-local:8080'),transport=httpx.MockTransport(handle),key_lookup=key).generate('Pourquoi c5 ?',request().fen,e)
    assert r.status=='test_double' and r.provider=='local_llm' and r.actual_model==r.requested_model==MODEL
    assert r.answer and r.usage.total_tokens==340 and len(calls)==2;key.assert_not_called()

@pytest.mark.parametrize('failure',['missing','timeout','http','malformed','models'])
def test_local_unavailable_is_deterministic_never_an_llm_answer(failure):
    e=evidence();calls=[]
    def handle(req):
        calls.append(req)
        if failure=='timeout':raise httpx.ReadTimeout('PRIVATE_PATH')
        if failure=='malformed':return httpx.Response(200,content=b'bad json')
        if failure=='models':return httpx.Response(200,json={'data':[]})
        return httpx.Response(503,json={'secret':'NOT_RETURNED'})
    r=HttpGenerator('local_llm',Settings(local_url='' if failure=='missing' else 'http://advisor-local:8080'),transport=httpx.MockTransport(handle)).generate('Question',request().fen,e)
    assert r.status=='deterministic' and r.provider=='deterministic' and r.answer is None and r.reason=='local_generator_unavailable'
    assert len(calls)<=1 and 'PRIVATE' not in r.model_dump_json() and 'NOT_RETURNED' not in r.model_dump_json()

def test_local_wrong_model_never_claims_answer():
    e=evidence()
    def handle(req):return httpx.Response(200,json={'data':[{'id':MODEL}]} if req.method=='GET' else local_envelope(e,model='other.gguf'))
    r=HttpGenerator('local_llm',Settings(local_url='http://advisor-local:8080'),transport=httpx.MockTransport(handle)).generate('Q',request().fen,e)
    assert r.status=='abstain' and r.reason=='LOCAL_MODEL_IDENTITY_CHANGED' and r.answer is None

def test_local_model_switch_is_discovered_per_submission_without_backend_reconfiguration():
    e=evidence();model=[MODEL]
    def handle(req):return httpx.Response(200,json={'data':[{'id':model[0]}]} if req.method=='GET' else local_envelope(e,model=model[0]))
    adapter=HttpGenerator('local_llm',Settings(local_url='http://advisor-local:8080'),transport=httpx.MockTransport(handle))
    assert adapter.generate('Q',request().fen,e).actual_model==MODEL
    model[0]='replacement.gguf';assert adapter.generate('Q',request().fen,e).actual_model=='replacement.gguf'

def test_context_budget_or_scope_never_requests_local_server():
    e=evidence();fake=Mock(side_effect=AssertionError('NO_HTTP'))
    r=HttpGenerator('local_llm',Settings(local_url='http://advisor-local:8080'),transport=fake).generate('Q',request().fen,e,intent='opening_theory')
    assert not r.executed and r.answer is None;fake.assert_not_called()
