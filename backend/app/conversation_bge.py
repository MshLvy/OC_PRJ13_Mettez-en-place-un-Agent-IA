"""Small backend adapter. No model/SDK import, no provider credential, no retry."""
import math,os
from threading import Lock
import httpx

COLLECTION='p13_openings_bge_1024_v1'
REVISION='5617a9f61b028005a4858fdac845db406aefb181'
CORPUS_SHA='7eb6b10749b1d09985139cb4fa89a5f2b11d75aa4ae2499e4614937923f86064'
class DenseUnavailable(Exception):pass
class BgeClient:
    def __init__(self,url=None,transport=None):
        self.url=os.environ.get('ADVISOR_BGE_URL','') if url is None else url
        self.transport=transport;self.gate=Lock()
    @property
    def configured(self):return bool(self.url)
    def search(self,question):
        # Fixed service endpoint only, never a URL from the HTTP user or a public provider.
        if self.url!='http://advisor-bge:8090':raise DenseUnavailable('BGE_CONFIGURATION_UNAVAILABLE')
        if not self.gate.acquire(blocking=False):raise DenseUnavailable('BGE_BUSY')
        try:
            with httpx.Client(timeout=12,transport=self.transport,trust_env=False,follow_redirects=False) as client:
                with client.stream('POST',self.url+'/search',json={'question':question}) as response:
                    if response.status_code!=200:raise DenseUnavailable('BGE_WORKER_UNAVAILABLE')
                    raw=b''
                    for block in response.iter_bytes():
                        raw+=block
                        if len(raw)>8192:raise DenseUnavailable('BGE_RESPONSE_INVALID')
            import json
            result=json.loads(raw)
            if not isinstance(result,dict) or result.get('collection')!=COLLECTION or result.get('revision')!=REVISION or result.get('dimension')!=1024 or result.get('model')!='BAAI/bge-m3' or result.get('corpus_sha256')!=CORPUS_SHA or result.get('entities_verified')!=96 or result.get('read_only') is not True or result.get('real_embedding_inference') is not True or result.get('real_milvus_query') is not True:raise DenseUnavailable('BGE_IDENTITY_CONFLICT')
            hits=result.get('hits');seen=set()
            if not isinstance(hits,list) or len(hits)>3:raise DenseUnavailable('BGE_RESPONSE_INVALID')
            for hit in hits:
                if not isinstance(hit,dict) or set(hit)!={'chunk_id','score'} or not isinstance(hit['chunk_id'],str) or hit['chunk_id'] in seen or type(hit['score']) not in (int,float) or not math.isfinite(hit['score']) or not -1.0001<=hit['score']<=1.0001:raise DenseUnavailable('BGE_RESPONSE_INVALID')
                seen.add(hit['chunk_id'])
            return hits
        except DenseUnavailable:raise
        except Exception:raise DenseUnavailable('BGE_WORKER_UNAVAILABLE') from None
        finally:self.gate.release()
