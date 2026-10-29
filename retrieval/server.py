"""Optional read-only query worker in the EXISTING pinned BGE tooling image.

No acquisition, ingestion, benchmarks, collection loading or lifecycle operation.
Standard-library HTTP server; heavy dependencies only in the worker process.
"""
import hashlib,json,logging,sys
from http.server import BaseHTTPRequestHandler,HTTPServer
from threading import Lock

COLLECTION='p13_openings_bge_1024_v1'
REVISION='5617a9f61b028005a4858fdac845db406aefb181'
CORPUS_SHA='7eb6b10749b1d09985139cb4fa89a5f2b11d75aa4ae2499e4614937923f86064'
class ReadOnlyClient:
    ALLOWED={'has_collection','describe_collection','describe_index','get_load_state','query','search'}
    def __init__(self,client):self._client=client
    def __getattr__(self,name):
        if name not in self.ALLOWED:raise ValueError('BGE_READ_ONLY_OPERATION')
        def call(*args,**kwargs):
            if not args or args[0]!=COLLECTION:raise ValueError('BGE_TARGET_CONFLICT')
            return getattr(self._client,name)(*args,**kwargs)
        return call

def artifact(rows):
    return hashlib.sha256(json.dumps(sorted((r['chunk_id'],r['vector_sha256']) for r in rows),separators=(',',':')).encode()).hexdigest()
class Runtime:
    def __init__(self,encoder,store):self.encoder,self.store=encoder,store;self.gate=Lock()
    def search(self,question):
        if not isinstance(question,str) or not question.strip() or len(question)>600:raise ValueError('BGE_QUERY_BUDGET')
        if not self.gate.acquire(blocking=False):raise ValueError('BGE_BUSY')
        try:
            self.store.verify();before=artifact(self.store.actual())
            vectors,proof=self.encoder.encode([question],'query')
            if proof.get('real_embedding_inference') is not True:raise ValueError('BGE_ENCODING_UNPROVEN')
            hits=self.store.search(vectors[0],k=3)
            self.store.verify()
            if artifact(self.store.actual())!=before:raise ValueError('BGE_COLLECTION_CHANGED')
            return {'collection':COLLECTION,'revision':REVISION,'dimension':1024,'model':'BAAI/bge-m3','corpus_sha256':CORPUS_SHA,'entities_verified':96,'read_only':True,'real_embedding_inference':True,'real_milvus_query':True,'hits':[{'chunk_id':i,'score':s} for i,s in hits]}
        finally:self.gate.release()

def load_runtime():
    # No model import in FastAPI. Original verifier checks pinned hashes,
    # dependency versions, architecture, CPU FP32 and CLS/L2 determinism.
    from retrieval.contract import documents,ROOT,policy
    from retrieval.preflight import resources
    from retrieval.encoder import Encoder
    from retrieval.store import Store
    p,docs=documents()
    if p['collection']!=COLLECTION or p['model']['revision']!=REVISION or hashlib.sha256((ROOT/'backend/app/data/advisor_v3/chunks.json').read_bytes()).hexdigest()!=CORPUS_SHA:raise ValueError('BGE_CORPUS_IDENTITY')
    res=resources()
    if res['available_memory_bytes'] is None or res['available_memory_bytes']<p['budget']['min_memory_free_bytes']:raise ValueError('BGE_MEMORY_HEADROOM')
    # The original model verifier distinguishes absent/invalid files/dependencies.
    encoder=Encoder('/models/bge')
    from pymilvus import MilvusClient,DataType
    logging.getLogger('pymilvus').handlers=[logging.NullHandler()];logging.getLogger('pymilvus').propagate=False
    client=MilvusClient(uri='http://milvus:19530',db_name='default',timeout=5)
    if str(client.get_server_version(timeout=5)).removeprefix('v')!='2.5.26':raise ValueError('BGE_SERVER_VERSION')
    store=Store(ReadOnlyClient(client),DataType,p,docs);store.verify()
    return Runtime(encoder,store)

class Handler(BaseHTTPRequestHandler):
    runtime=None
    def log_message(self,*args):pass # no question, path, content or SDK exception logging
    def send(self,status,data):
        raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.send(200 if self.path=='/health' else 404,{'status':'ready' if self.path=='/health' else 'not_found'})
    def do_POST(self):
        self.connection.settimeout(3)
        if self.path!='/search':return self.send(404,{'code':'NOT_FOUND'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 1<=length<=4096 or self.headers.get('Transfer-Encoding'):return self.send(413,{'code':'BGE_REQUEST_BUDGET'})
            body=json.loads(self.rfile.read(length))
            if not isinstance(body,dict) or set(body)!={'question'}:return self.send(400,{'code':'BGE_REQUEST_INVALID'})
            result=self.runtime.search(body['question']);self.send(200,result)
        except Exception:self.send(503,{'code':'BGE_QUERY_UNAVAILABLE'})

def main():
    try:Handler.runtime=load_runtime()
    except Exception as error:
        allowed={'BGE_MODEL_DIRECTORY_MISSING','BGE_MODEL_FILE_MISSING','BGE_MODEL_SHA','BGE_MODEL_SIZE_OR_SYMLINK','BGE_MODEL_FILE_SET','BGE_DEPENDENCY_VERSIONS','BGE_MEMORY_HEADROOM','BGE_SERVER_VERSION','BGE_CORPUS_IDENTITY','COLLECTION_INCOMPLETE','DEVELOPMENT_COLLECTION_NOT_LOADED','COLLECTION_OWNERSHIP_OR_SCHEMA_CONFLICT','SAME_ID_CONTENT_OR_FOREIGN_ROW_CONFLICT','STORED_VECTOR_DIGEST_CONFLICT'}
        code=str(error) if str(error) in allowed else 'BGE_DEPENDENCY_MISSING' if isinstance(error,ImportError) else 'BGE_WORKER_START_UNAVAILABLE'
        print(code,file=sys.stderr);return 1
    HTTPServer(('0.0.0.0',8090),Handler).serve_forever()
if __name__=='__main__':sys.exit(main())
