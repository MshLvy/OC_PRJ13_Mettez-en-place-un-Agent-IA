"""Offline regression of local compact profile; no inference or private outputs."""
import hashlib,json
import httpx,pytest
from pydantic import ValidationError
from app import conversation_local as compact
from app.conversation_generators import HttpGenerator,Settings
from app.conversation import ConversationService
from app.conversation_mistral import build_prompt
from test_generation_local import evidence,local_envelope,MODEL
from test_conversation import request


def run(output=None,*,scope='position',finish='stop',timings=None):
    e=ConversationService().ask(request([] if scope=='opening_theory' else ['e2e4','c7c5'],intent=scope,request_generation=False)).passages
    calls=[]
    def handle(req):
        calls.append(req)
        if req.method=='GET':return httpx.Response(200,json={'data':[{'id':MODEL}]})
        payload=json.loads(req.content)
        assert payload['max_tokens']==128 and payload['cache_prompt'] is True
        schema=payload['response_format']['schema']
        assert schema['additionalProperties'] is False and schema['properties']['scope']['enum']==[scope]
        raw=local_envelope(e,scope);raw['choices'][0]['finish_reason']=finish
        if output is not None:raw['choices'][0]['message']['content']=output if isinstance(output,str) else json.dumps(output)
        if timings is not None:raw['timings']=timings
        return httpx.Response(200,json=raw)
    result=HttpGenerator('local_llm',Settings(local_url='http://advisor-local:8080'),transport=httpx.MockTransport(handle)).generate('Pourquoi c5 ?',request([] if scope=='opening_theory' else ['e2e4','c7c5']).fen,e,intent=scope,history=['SECRET_HISTORY_NOT_FOR_PROMPT'])
    assert len(calls)==2
    return result,e,calls

@pytest.mark.parametrize('scope',['position','opening_theory'])
def test_compact_positive_strict_scope_and_phase_timings(scope):
    r,e,calls=run(scope=scope,timings={'prompt_ms':10,'predicted_ms':20})
    assert r.status=='test_double' and r.answer.scope==scope
    assert r.answer.paragraphs[0].citation_ids==[e[0].chunk_id]
    assert r.timings['server_prompt_ms']==10 and r.timings['server_generation_ms']==20
    for field in ('prompt_ms','discovery_ms','inference_http_ms','validation_ms','context_validation_ms'):assert r.timings[field]>=0
    assert 'SECRET_HISTORY' not in calls[-1].content.decode()
    assert r.context_proof['history_included'] is False

@pytest.mark.parametrize('output,code',[
    ('PRIVATE_BROKEN_JSON','JSON_SYNTAX_INVALID'),
    ({'scope':'position','text':'Texte','cite':['S3']},'UNKNOWN_CITATION_ALIAS'),
    ({'scope':'position','text':'Texte','cite':[]},'MISSING_CITATION'),
    ({'scope':'position','text':'Texte','cite':['S1','S1']},'DUPLICATE_CITATION'),
    ({'scope':'opening_theory','text':'Texte','cite':['S1']},'OUTPUT_SCOPE_MISMATCH'),
    ({'scope':'position','text':'e2e5','cite':['S1']},'UNDECLARED_UCI'),
    ({'scope':'position','text':'X\nY','cite':['S1']},'UNSAFE_OUTPUT'),
    ({'scope':'position','text':'','cite':['S1']},'ABSTAIN_WITH_ANSWER'),
    ({'scope':'position','text':'X'*241,'cite':['S1']},'COMPACT_SCHEMA_INVALID'),
    ({'scope':'position','text':'Texte','cite':['S1'],'moves_uci':[]},'COMPACT_SCHEMA_INVALID'),
    ({'scope':'position','abstain':False,'paragraphs':[],'moves_uci':[]},'COMPACT_SCHEMA_INVALID'),
])
def test_compact_rejection_is_precise_and_sanitized(output,code):
    r,_,_=run(output)
    assert r.status=='abstain' and r.answer is None and r.validation_code==code
    assert r.error_code=='GENERATION_OUTPUT_REJECTED'
    assert 'PRIVATE_BROKEN_JSON' not in r.model_dump_json()


def test_theory_rejects_position_claim():
    r,_,_=run({'scope':'opening_theory','text':'Jouez maintenant dans votre position.','cite':['S1']},scope='opening_theory')
    assert r.validation_code=='THEORY_POSITION_CLAIM' and r.answer is None


def test_explicit_empty_answer_is_abstention():
    r,_,_=run({'scope':'position','text':'','cite':[]})
    assert r.status=='abstain' and r.reason=='MODEL_ABSTAINED' and r.validation_code is None


def test_length_never_salvaged_even_valid_json_retains_usage_and_no_retry():
    r,_,_=run(finish='length',timings={'prompt_ms':11,'predicted_ms':22})
    assert r.status=='abstain' and r.reason=='GENERATION_OUTPUT_TRUNCATED' and r.answer is None
    assert r.usage.completion_tokens==40 and r.timings['server_generation_ms']==22
    assert 'validation_ms' not in r.timings

@pytest.mark.parametrize('value',[True,-1,'12',None])
def test_invalid_server_timings_not_invented(value):
    r,_,_=run(timings={'prompt_ms':value,'predicted_ms':value})
    assert not {'server_prompt_ms','server_generation_ms'}&r.timings.keys()


def test_prompt_repeatable_exact_offsets_hashes_and_identity_no_mutation():
    e=evidence();before=[r.model_dump() for r in e]
    a=compact.prepare('Pourquoi c5 ?',request().fen,e,intent='position')
    assert a==compact.prepare('Pourquoi c5 ?',request().fen,e,intent='position')
    messages,schema,mapping,selected,proof=a
    body=json.loads(messages[1]['content'])
    assert 1<=len(selected)<=2 and proof['prompt_bytes']<=4096
    assert len(json.dumps(build_prompt('Pourquoi c5 ?',request().fen,e),ensure_ascii=False).encode())>proof['prompt_bytes']
    for item,source in zip(proof['sources'],body['sources']):
        row=mapping[item['ref']];text=row.text[item['start']:item['end']]
        assert text==source['text'] and len(text)<=640
        assert item['excerpt_sha256']==hashlib.sha256(text.encode()).hexdigest()
        assert item['text_sha256']==row.text_sha256 and item['chunk_id']==row.chunk_id
    assert before==[r.model_dump() for r in e]


def test_no_truncated_sentence_or_stitching():
    text='Sans rapport. Le pion c5 attaque le centre. Il ne gagne pas forcément du matériel.'
    start,end,content=compact.excerpt(text,{'c5'})
    assert content==text[start:end] and content.endswith('.')
    with pytest.raises(ValueError,match='LOCAL_EXCERPT_UNAVAILABLE'):compact.excerpt('c5 '+'x'*700,{'c5'})


def test_service_overall_timing_metadata_is_separate():
    r=ConversationService().ask(request(request_generation=False))
    assert r.timings['total_ms']>=0 and r.timings['retrieval_ms']>=0 and r.timings['generation_ms'] is None
