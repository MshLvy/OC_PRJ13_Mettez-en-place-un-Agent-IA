"""Mode-selected local/API generators. No request/secret read at construction.

Only the explicit admitted conversation submission can call generate_context.
"""
from dataclasses import dataclass
import json,os,re,time,math
from pydantic import ValidationError
from app import conversation_local as compact
from threading import Lock
import httpx
from app.conversation_mistral import Generation,Usage,build_prompt,validate_output

MODEL_ID=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$')
APPROVED_API={'mistral':'https://api.mistral.ai/v1/chat/completions','groq':'https://api.groq.com/openai/v1/chat/completions'}
GROQ_MODEL='openai/gpt-oss-120b'
def valid_model(value,provider):
    return isinstance(value,str) and (value==GROQ_MODEL if provider=='groq_api' else bool(MODEL_ID.fullmatch(value)))
def api_identity(settings):
    return ('groq_api','Groq') if settings.api_provider=='groq' else ('mistral_api','Mistral')
LOCAL_ENDPOINT='http://advisor-local:8080'
PROMPT_VERSION='p13-grounded-v2'
def secret_value(name):
    # Called only after a valid, explicit live request with admitted evidence.
    return os.environ.get(name,'')
class Failure(Exception):pass

@dataclass(frozen=True)
class Settings:
    local_url:str=''
    local_timeout:float=45
    api_provider:str='mistral'
    api_model:str='mistral-small-latest'
    api_endpoint:str=APPROVED_API['mistral']
    api_secret_env:str='MISTRAL_API_KEY'
    api_timeout:float=15
    # Legacy fallback remains supported; None/empty means no legacy override.
    max_tokens:int|None=None
    local_max_tokens:int|None=None
    mistral_max_tokens:int|None=None
    groq_max_tokens:int|None=None
    groq_reasoning_effort:str='low'
    @classmethod
    def from_env(cls):
        try:
            def optional_int(name):
                value=os.environ.get(name)
                if value in (None,''):return None
                if not re.fullmatch(r'[0-9]+',value):raise ValueError('INVALID_TOKEN_BUDGET')
                return int(value)
            settings=cls(local_url=os.environ.get('LOCAL_LLM_URL',''),local_timeout=float(os.environ.get('LOCAL_LLM_TIMEOUT_SECONDS','45')),
                api_provider=os.environ.get('ADVISOR_API_PROVIDER','mistral'),api_model=os.environ.get('ADVISOR_API_MODEL','mistral-small-latest'),
                api_endpoint=os.environ.get('ADVISOR_API_ENDPOINT',APPROVED_API['mistral']),api_secret_env=os.environ.get('ADVISOR_API_SECRET_ENV','MISTRAL_API_KEY'),
                api_timeout=float(os.environ.get('ADVISOR_API_TIMEOUT_SECONDS','15')),max_tokens=optional_int('GENERATION_MAX_TOKENS'),local_max_tokens=optional_int('LOCAL_LLM_MAX_TOKENS'),mistral_max_tokens=optional_int('MISTRAL_MAX_TOKENS'),groq_max_tokens=optional_int('GROQ_MAX_TOKENS'),groq_reasoning_effort=os.environ.get('GROQ_REASONING_EFFORT','low'))
            settings.validate_budgets();return settings
        except (ValueError,TypeError):raise Failure('GENERATION_CONFIGURATION_INVALID') from None
    def validate_budgets(self):
        if not 1<=self.local_timeout<=45 or not 1<=self.api_timeout<=20:raise Failure('GENERATION_CONFIGURATION_INVALID')
        for value,ceiling in ((self.max_tokens,512),(self.local_max_tokens,compact.MAX_TOKENS),(self.mistral_max_tokens,512),(self.groq_max_tokens,2048)):
            if value is not None and (type(value) is not int or not 64<=value<=ceiling):raise Failure('GENERATION_CONFIGURATION_INVALID')
        if self.groq_reasoning_effort not in ('low','medium','high'):raise Failure('GENERATION_CONFIGURATION_INVALID')
    def output_budget(self,provider):
        self.validate_budgets()
        explicit,default={'local_llm':(self.local_max_tokens,128),'mistral_api':(self.mistral_max_tokens,512),'groq_api':(self.groq_max_tokens,2048)}[provider]
        value=explicit if explicit is not None else self.max_tokens if self.max_tokens is not None else default
        return min(value,compact.MAX_TOKENS) if provider=='local_llm' else value
    def validate(self,provider):
        self.validate_budgets()
        if provider=='local_llm':
            if not self.local_url:raise Failure('LOCAL_LLM_NOT_CONFIGURED')
            if self.local_url!=LOCAL_ENDPOINT:raise Failure('LOCAL_LLM_ENDPOINT_REJECTED')
        else:
            secret_allowed=self.api_secret_env=='GROQ_API_KEY' if self.api_provider=='groq' else bool(re.fullmatch(r'MISTRAL_[A-Z0-9_]{1,50}',self.api_secret_env))
            if self.api_provider not in APPROVED_API or provider!=api_identity(self)[0] or self.api_endpoint!=APPROVED_API[self.api_provider] or not valid_model(self.api_model,provider) or not secret_allowed:raise Failure('API_CONFIGURATION_REJECTED')

def deterministic(reason,*,attempted=False,requested_model=None,duration_ms=0,timings=None,context_proof=None):
    return Generation(status='deterministic',provider='deterministic',engine='deterministic',model='documentary-extracts-v1',
        requested_model=requested_model,attempted_provider='local_llm',executed=attempted,reason='local_generator_unavailable',error_code=reason,duration_ms=duration_ms,timings=timings or {},context_proof=context_proof,prompt_version=compact.VERSION)

def contains_secret(value,secret):
    if isinstance(value,str):return secret in value
    if isinstance(value,dict):return any(contains_secret(k,secret) or contains_secret(v,secret) for k,v in value.items())
    if isinstance(value,list):return any(contains_secret(v,secret) for v in value)
    return False

class HttpGenerator:
    def __init__(self,provider,settings,*,transport=None,key_lookup=None):
        self.provider=provider;self.settings=settings;self.transport=transport;self.key_lookup=key_lookup or secret_value
    def _read(self,client,method,url,*,payload=None,headers=None):
        try:
            with client.stream(method,url,json=payload,headers=headers,**({'timeout':min(3,self.settings.local_timeout)} if method=='GET' else {})) as response:
                status=response.status_code
                if status in (401,403):raise Failure('GENERATOR_AUTH_UNAVAILABLE')
                if status==429:raise Failure('PROVIDER_RATE_LIMITED')
                if status>=500:raise Failure('PROVIDER_SERVER_ERROR')
                if status!=200:raise Failure('GENERATOR_HTTP_ERROR')
                raw=b''
                for block in response.iter_bytes():
                    raw+=block
                    if len(raw)>65536:raise Failure('GENERATOR_RESPONSE_TOO_LARGE')
            return json.loads(raw)
        except httpx.TimeoutException:raise Failure('GENERATOR_TIMEOUT') from None
        except httpx.HTTPError:raise Failure('GENERATOR_CONNECTION_UNAVAILABLE') from None
        except (ValueError,UnicodeError):raise Failure('GENERATOR_JSON_INVALID') from None
    def generate(self,question,fen,evidence,*,intent='position',history=None):
        start=time.monotonic();attempted=False;requested=None;actual=None;usage=None;credential=''
        timings={};validation_code=None;context_proof=None;mapping=None;selected=evidence
        local=self.provider=='local_llm';engine='llama.cpp' if local else ('Groq' if self.provider=='groq_api' else 'Mistral')
        def result(status,reason,answer=None,error=None):
            safe_default='local-unavailable' if local else (self.settings.api_model if valid_model(self.settings.api_model,self.provider) else ('groq-unavailable' if self.provider=='groq_api' else 'mistral-unavailable'))
            safe_requested=None if credential and requested and credential in requested else requested
            safe_actual=None if credential and actual and credential in actual else actual
            if credential and credential in safe_default:safe_default='api-unavailable'
            return Generation(status=status,provider=self.provider,engine=engine,model=safe_actual or safe_requested or safe_default,
                requested_model=safe_requested,actual_model=safe_actual,executed=attempted,answer=answer,reason=reason,error_code=error,
                duration_ms=round((time.monotonic()-start)*1000,2),usage=usage,test_transport=self.transport is not None,
                timings=timings,validation_code=validation_code,context_proof=context_proof,prompt_version=compact.VERSION if local else PROMPT_VERSION)
        try:
            self.settings.validate(self.provider)
            # Same scope and trust checks before any HTTP or secret lookup.
            try:
                t=time.monotonic()
                validate_output({'scope':intent,'abstain':True,'paragraphs':[],'moves_uci':[]},fen,evidence,intent=intent)
                timings['context_validation_ms']=round((time.monotonic()-t)*1000,2)
                t=time.monotonic()
                if local:messages,schema,mapping,selected,context_proof=compact.prepare(question,fen,evidence,intent=intent)
                else:messages=build_prompt(question,fen,evidence,intent=intent,history=history)
                timings['prompt_ms']=round((time.monotonic()-t)*1000,2)
            except ValueError as error:
                code='GENERATION_CONTEXT_BUDGET' if str(error)=='GENERATION_CONTEXT_BUDGET' else 'GENERATION_CONTEXT_REJECTED'
                return result('abstain',code,error=code)
            timeout=self.settings.local_timeout if local else self.settings.api_timeout
            headers={}
            if not local:
                requested=self.settings.api_model
                key=self.key_lookup(self.settings.api_secret_env)
                if not isinstance(key,str) or not key or len(key)>4096 or any(c.isspace() for c in key):raise Failure('GROQ_KEY_UNAVAILABLE' if self.provider=='groq_api' else 'MISTRAL_KEY_UNAVAILABLE')
                credential=key
                headers={'Authorization':'Bearer '+key}
            # Local internal traffic ignores proxy settings; API traffic uses
            # the deployment's normal proxy and certificate trust (TLS enabled).
            with httpx.Client(timeout=httpx.Timeout(timeout,connect=min(2,timeout)),transport=self.transport,trust_env=not local,follow_redirects=False) as client:
                if local:
                    t=time.monotonic()
                    try:models=self._read(client,'GET',self.settings.local_url+'/v1/models')
                    finally:timings['discovery_ms']=round((time.monotonic()-t)*1000,2)
                    entries=models.get('data') if isinstance(models,dict) else None
                    if not isinstance(entries,list) or len(entries)!=1 or not isinstance(entries[0],dict) or not isinstance(entries[0].get('id'),str) or not MODEL_ID.fullmatch(entries[0]['id']):raise Failure('LOCAL_MODEL_DISCOVERY_INVALID')
                    requested=entries[0]['id']
                payload={'model':requested,'messages':messages,'response_format':{'type':'json_object'},'temperature':0,'stream':False,'max_tokens':self.settings.output_budget(self.provider)}
                if local:
                    payload['response_format']={'type':'json_object','schema':schema}
                    payload['cache_prompt']=True
                if self.provider=='groq_api':
                    # Completion budget includes GPT-OSS reasoning; never consume
                    # reasoning text as an answer or request unsupported reasoning_format.
                    payload['max_completion_tokens']=payload.pop('max_tokens')
                    payload['reasoning_effort']=self.settings.groq_reasoning_effort
                else:payload['seed' if local else 'random_seed']=0
                attempted=True
                t=time.monotonic()
                try:raw=self._read(client,'POST',self.settings.local_url+'/v1/chat/completions' if local else self.settings.api_endpoint,payload=payload,headers=headers)
                finally:timings['inference_http_ms']=round((time.monotonic()-t)*1000,2)
            if credential and contains_secret(raw,credential):raise Failure('GENERATOR_SENSITIVE_RESPONSE_REJECTED')
            if not isinstance(raw,dict) or not isinstance(raw.get('model'),str) or not valid_model(raw['model'],self.provider):raise Failure('GENERATOR_ENVELOPE_INVALID')
            if local and raw['model']!=requested:raise Failure('LOCAL_MODEL_IDENTITY_CHANGED')
            actual=raw['model']
            if raw.get('usage') is not None:
                try:
                    u=raw['usage'];usage=Usage.model_validate({k:u[k] for k in ('prompt_tokens','completion_tokens','total_tokens')})
                    if usage.total_tokens!=usage.prompt_tokens+usage.completion_tokens:raise ValueError()
                except Exception:raise Failure('GENERATOR_USAGE_INVALID') from None
            if local and isinstance(raw.get('timings'),dict):
                for field,name in (('prompt_ms','server_prompt_ms'),('predicted_ms','server_generation_ms')):
                    value=raw['timings'].get(field)
                    if type(value) in (int,float) and math.isfinite(value) and 0<=value<=3600000:timings[name]=float(value)
            choices=raw.get('choices')
            if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):raise Failure('GENERATOR_ENVELOPE_INVALID')
            choice=choices[0]
            if choice.get('finish_reason')=='length':raise Failure('GENERATION_OUTPUT_TRUNCATED')
            if choice.get('finish_reason')!='stop':raise Failure('GENERATION_FINISH_REJECTED')
            message=choice.get('message')
            if not isinstance(message,dict) or message.get('role')!='assistant' or not isinstance(message.get('content'),str):raise Failure('GENERATOR_ENVELOPE_INVALID')
            t=time.monotonic()
            try:
                parsed=json.loads(message['content'])
                answer=compact.decode(parsed,fen,mapping,selected,intent=intent) if local else validate_output(parsed,fen,evidence,intent=intent)
            except json.JSONDecodeError:
                validation_code='JSON_SYNTAX_INVALID';raise Failure('GENERATION_OUTPUT_REJECTED') from None
            except ValidationError:
                validation_code='COMPACT_SCHEMA_INVALID' if local else 'OUTPUT_SCHEMA_INVALID';raise Failure('GENERATION_OUTPUT_REJECTED') from None
            except Exception as error:
                allowed={'OUTPUT_SCOPE_MISMATCH','UNKNOWN_CITATION_ALIAS','DUPLICATE_CITATION','MISSING_CITATION','FABRICATED_CITATION','ABSTAIN_WITH_ANSWER','EMPTY_ANSWER','UNSAFE_OUTPUT','UNDECLARED_UCI','THEORY_POSITION_CLAIM','THEORY_MOVES_NOT_ALLOWED'}
                validation_code=str(error) if str(error) in allowed else 'OUTPUT_VALIDATION_FAILED'
                raise Failure('GENERATION_OUTPUT_REJECTED') from None
            finally:timings['validation_ms']=round((time.monotonic()-t)*1000,2)
            if answer.abstain:return result('abstain','MODEL_ABSTAINED')
            return result('test_double' if self.transport is not None else 'generated','SOURCED_GENERATION',answer)
        except Failure as error:
            code=str(error)
            if local and code not in ('GENERATION_OUTPUT_REJECTED','GENERATION_OUTPUT_TRUNCATED','GENERATION_FINISH_REJECTED','LOCAL_MODEL_IDENTITY_CHANGED','GENERATOR_USAGE_INVALID'):
                return deterministic(code,attempted=attempted,requested_model=requested,duration_ms=round((time.monotonic()-start)*1000,2),timings=timings,context_proof=context_proof)
            return result('abstain' if attempted and code not in ('GENERATOR_TIMEOUT','GENERATOR_CONNECTION_UNAVAILABLE','PROVIDER_RATE_LIMITED','PROVIDER_SERVER_ERROR','GENERATOR_AUTH_UNAVAILABLE','GENERATOR_HTTP_ERROR') else 'provider_unavailable',code,error=code)
        except Exception:
            # Never return provider bodies, exceptions, credentials or private paths.
            if local:return deterministic('LOCAL_GENERATOR_UNAVAILABLE',attempted=attempted,requested_model=requested,duration_ms=round((time.monotonic()-start)*1000,2),timings=timings,context_proof=context_proof)
            return result('abstain' if attempted else 'provider_unavailable','GENERATOR_RESPONSE_INVALID',error='GENERATOR_RESPONSE_INVALID')

class GeneratorRouter:
    def __init__(self,settings_factory=Settings.from_env,*,local_transport=None,api_transport=None,key_lookup=None):
        self.settings_factory=settings_factory;self.local_transport=local_transport;self.api_transport=api_transport;self.key_lookup=key_lookup;self.gate=Lock()
    def generate_context(self,body,fen,evidence):
        if not body.request_generation:return Generation(status='generation_disabled')
        local=body.demo_mode=='simulation'
        try:settings=self.settings_factory()
        except Exception:
            return deterministic('GENERATION_CONFIGURATION_INVALID') if local else Generation(status='provider_unavailable',model='api-unavailable',reason='GENERATION_CONFIGURATION_INVALID')
        provider,engine=('local_llm','llama.cpp') if local else api_identity(settings)
        if not self.gate.acquire(blocking=False):
            return deterministic('GENERATOR_BUSY') if local else Generation(status='provider_unavailable',provider=provider,engine=engine,model=settings.api_model if valid_model(settings.api_model,provider) else 'api-unavailable',reason='GENERATOR_BUSY')
        try:
            generator=HttpGenerator(provider,settings,transport=self.local_transport if provider=='local_llm' else self.api_transport,key_lookup=self.key_lookup)
            return generator.generate(body.question,fen,evidence,intent=body.intent,history=body.history)
        finally:self.gate.release()
