"""Optional local sessions. Only explicit CRUD writes; no memory persistence fallback."""
import base64,hashlib,hmac,json,os,re,secrets,time
from datetime import datetime,timezone
from threading import Lock
from typing import Literal,Protocol
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,model_validator,field_validator
from app.game import HistoryRequest,rebuild,snapshot
from app.positions import diagnose_fen
from app.conversation_mistral import Output,validate_output

ID=r'^[a-f0-9]{32}$'
Opening=Literal['espagnole','italienne','sicilienne','francaise','caro_kann','gambit_dame']
class SessionFailure(Exception):
    def __init__(self,code,status=503):self.code=code;self.status=status;super().__init__(code)
def safe_text(text):
    # No credential lookup is needed to reject common accidental credential pastes.
    import unicodedata
    if any(unicodedata.category(c) in ('Cc','Cf','Cs') for c in text) or re.search(r'(?i)(api[_ -]?key|authorization|bearer\s|-----BEGIN|AIza[A-Za-z0-9_-]{20}|gsk_[A-Za-z0-9]{15}|sk-[A-Za-z0-9]{15}|[A-Za-z0-9_-]{32,})',text):raise ValueError('PRIVATE_OR_UNSAFE_TEXT')
    return text
class Closed(BaseModel):model_config=ConfigDict(extra='forbid')
class Position(HistoryRequest):
    history:list[str]=Field(max_length=256)
    fen:str=Field(strict=True,max_length=256)
    snapshot:str=Field(pattern=r'^[a-f0-9]{64}$')
    @model_validator(mode='after')
    def coherent(self):
        board,_=rebuild(self.history)
        if diagnose_fen(self.fen).fen_normalized!=board.fen(en_passant='fen') or snapshot(self.history)!=self.snapshot:raise ValueError('SESSION_POSITION_MISMATCH')
        self.fen=board.fen(en_passant='fen');return self
class SessionDraft(Position):
    opening:Opening
    receipts:list[str]=Field(default_factory=list,max_length=5)
    @field_validator('receipts')
    @classmethod
    def bounded(cls,values):
        if any(not isinstance(v,str) or len(v)>32768 for v in values):raise ValueError('INVALID_RECEIPT')
        if len(set(values))!=len(values):raise ValueError('DUPLICATE_RECEIPT')
        return values
class Citation(Closed):
    chunk_id:str=Field(pattern=r'^v3e-[a-z0-9-]{1,150}$')
    text_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    license:Literal['CC-BY-SA-4.0']='CC-BY-SA-4.0'
    corpus_version:Literal['pilot-fr-v3-enriched-0.1']='pilot-fr-v3-enriched-0.1'
class Exchange(Closed):
    question:str=Field(strict=True,min_length=1,max_length=600)
    answer:Output
    intent:Literal['position','opening_theory']
    provider:Literal['local_llm','groq_api','mistral_api']
    engine:Literal['llama.cpp','Groq','Mistral']
    model:str=Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.\-/]{0,159}$')
    retrieval_mode:Literal['offline_bm25_v3','hybrid_bm25_bge_v3','bm25_fallback_v3']
    citations:list[Citation]=Field(min_length=1,max_length=3)
    review:Literal['application_checks_only_human_pending']='application_checks_only_human_pending'
    @model_validator(mode='after')
    def checked(self):
        safe_text(self.question)
        if self.answer.abstain or not self.answer.paragraphs or self.answer.scope!=self.intent or self.intent=='opening_theory' and self.answer.moves_uci:raise ValueError('UNAPPROVED_ANSWER')
        ids={c.chunk_id for c in self.citations}
        for p in self.answer.paragraphs:
            safe_text(p.text)
            if not set(p.citation_ids)<=ids:raise ValueError('UNAPPROVED_CITATION')
        return self
class SessionRecord(Position):
    schema_version:Literal[1]=1
    id:str=Field(pattern=ID)
    opening:Opening
    created_at:str=Field(max_length=40,pattern=r'^\d{4}-\d{2}-\d{2}T[0-9:.]+(?:\+00:00|Z)$')
    updated_at:str=Field(max_length=40,pattern=r'^\d{4}-\d{2}-\d{2}T[0-9:.]+(?:\+00:00|Z)$')
    exchanges:list[Exchange]=Field(default_factory=list,max_length=5)
    @model_validator(mode='after')
    def exchanges_legal(self):
        import chess
        for e in self.exchanges:
            board=chess.Board(self.fen)
            for move in e.answer.moves_uci:board.push_uci(move)
        return self

class Receipts:
    """Stateless signed response attestation; ephemeral key, 15 minute validity.

    No DB, transcript cache, secret env lookup or automatic recording.
    """
    def __init__(self,clock=time.time):self.key=secrets.token_bytes(32);self.clock=clock
    def issue(self,body,result):
        g=result.generation
        if not body.request_generation or result.status!='answered' or g.status!='generated' or g.test_transport or not g.answer or body.history is None:return None
        try:
            Position(history=body.history,fen=body.fen,snapshot=result.snapshot)
            answer=validate_output(g.answer.model_dump(),result.fen,result.passages,intent=body.intent)
            used={c for p in answer.paragraphs for c in p.citation_ids}
            rows=[p for p in result.passages if p.chunk_id in used]
            exchange=Exchange(question=body.question,answer=answer,intent=body.intent,provider=g.provider,engine=g.engine,model=g.actual_model or g.model,retrieval_mode=result.retrieval_mode,citations=[Citation(chunk_id=p.chunk_id,text_sha256=p.text_sha256) for p in rows])
            data={'exp':int(self.clock())+900,'fen':result.fen,'snapshot':result.snapshot,'families':sorted({p.family.replace('_','-') for p in rows}),'exchange':exchange.model_dump()}
            raw=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
            if len(raw)>24000:return None
            token=base64.urlsafe_b64encode(raw).decode()+'.'+hmac.new(self.key,raw,hashlib.sha256).hexdigest()
            return token
        except (ValueError,TypeError):return None
    def read(self,token,draft):
        try:
            encoded,mac=token.split('.')
            raw=base64.b64decode(encoded,altchars=b'-_',validate=True)
            if not hmac.compare_digest(hmac.new(self.key,raw,hashlib.sha256).hexdigest(),mac):raise ValueError()
            obj=json.loads(raw)
            if type(obj['exp']) is not int or obj['exp']<self.clock() or obj['fen']!=draft.fen or obj['snapshot']!=draft.snapshot or obj['families']!=[draft.opening.replace('_','-')]:raise ValueError()
            return Exchange.model_validate(obj['exchange'])
        except Exception:raise SessionFailure('SESSION_RECEIPT_INVALID_OR_EXPIRED',422) from None

class SessionStore(Protocol):
    def insert(self,document):...
    def list(self,after,limit):...
    def get(self,ident):...
    def delete(self,ident):...
    def close(self):...
class MongoStore:
    """Driver import, secret lookup and connection are lazy, CRUD-only."""
    def __init__(self,enabled=None,password_lookup=None,client_factory=None):
        self.mode=os.environ.get('MONGO_ENABLED','false') if enabled is None else enabled
        self.password_lookup=password_lookup or (lambda:os.environ.get('MONGO_PASSWORD',''))
        self.client_factory=client_factory;self.client=None;self.lock=Lock()
    def status(self):return 'disabled' if self.mode=='false' else 'configured_not_probed' if self.mode=='true' else 'unavailable'
    def collection(self):
        if self.mode=='false':raise SessionFailure('SESSIONS_DISABLED')
        if self.mode!='true':raise SessionFailure('MONGO_CONFIGURATION_INVALID')
        with self.lock:
            if self.client is None:
                try:
                    password=self.password_lookup()
                    if not isinstance(password,str) or not re.fullmatch(r'[a-f0-9]{64}',password):raise ValueError()
                    factory=self.client_factory
                    if factory is None:
                        from pymongo import MongoClient
                        factory=MongoClient
                    self.client=factory('mongodb://mongodb:27017',username='p13_sessions',password=password,authSource='p13_sessions',connect=False,serverSelectionTimeoutMS=700,connectTimeoutMS=700,socketTimeoutMS=700,timeoutMS=1500,retryReads=False,retryWrites=False,w=1,journal=True,maxPoolSize=2,minPoolSize=0,appname='p13-sessions')
                except Exception:raise SessionFailure('SESSIONS_UNAVAILABLE') from None
        return self.client['p13_sessions']['sessions']
    def perform(self,fn):
        try:return fn(self.collection())
        except SessionFailure:raise
        except Exception:raise SessionFailure('SESSIONS_UNAVAILABLE') from None
    def insert(self,document):
        def write(c):
            result=c.insert_one(document)
            if not result.acknowledged:raise SessionFailure('SESSION_WRITE_UNCONFIRMED')
        self.perform(write)
    def list(self,after,limit):return self.perform(lambda c:list(c.find({'_id':{'$gt':after}} if after else {},{'_id':1,'opening':1,'created_at':1,'updated_at':1}).sort('_id',1).limit(limit)))
    def get(self,ident):return self.perform(lambda c:c.find_one({'_id':ident}))
    def delete(self,ident):
        def remove(c):
            r=c.delete_one({'_id':ident})
            if not r.acknowledged:raise SessionFailure('SESSION_DELETE_UNCONFIRMED')
            return r.deleted_count==1
        return self.perform(remove)
    def close(self):
        if self.client is not None:self.client.close()
class SessionSummary(Closed):
    id:str=Field(pattern=ID)
    opening:Opening
    created_at:str=Field(max_length=40,pattern=r'^\d{4}-\d{2}-\d{2}T[0-9:.]+(?:\+00:00|Z)$')
    updated_at:str=Field(max_length=40,pattern=r'^\d{4}-\d{2}-\d{2}T[0-9:.]+(?:\+00:00|Z)$')

class SessionService:
    def __init__(self,store,receipts):self.store=store;self.receipts=receipts
    def create(self,draft):
        exchanges=[self.receipts.read(t,draft) for t in draft.receipts]
        now=datetime.now(timezone.utc).isoformat()
        record=SessionRecord(**draft.model_dump(exclude={'receipts'}),id=uuid4().hex,created_at=now,updated_at=now,exchanges=exchanges)
        document=record.model_dump();document['_id']=document.pop('id')
        if len(json.dumps(document,ensure_ascii=False).encode())>65536:raise SessionFailure('SESSION_TOO_LARGE',422)
        self.store.insert(document);return record
    def get(self,ident):
        data=self.store.get(ident)
        if data is None:raise SessionFailure('SESSION_NOT_FOUND',404)
        try:
            data=dict(data);data['id']=data.pop('_id');return SessionRecord.model_validate(data)
        except Exception:raise SessionFailure('SESSION_DATA_INVALID') from None
    def list(self,after,limit):
        rows=self.store.list(after,limit+1);items=[]
        for row in rows[:limit]:
            ident=row.get('_id')
            if not isinstance(ident,str) or not re.fullmatch(ID,ident):raise SessionFailure('SESSION_DATA_INVALID')
            try:items.append(SessionSummary(id=ident,opening=row['opening'],created_at=row['created_at'],updated_at=row['updated_at']).model_dump())
            except Exception:raise SessionFailure('SESSION_DATA_INVALID') from None
        return {'items':items,'next_cursor':items[-1]['id'] if len(rows)>limit and items else None}

    def delete(self,ident):
        """One acknowledged storage operation, no automatic replay."""
        if not self.store.delete(ident):raise SessionFailure('SESSION_NOT_FOUND',404)
        return {'status':'deleted','id':ident}
