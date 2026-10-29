"""Bootstrap only the release collection in its separate Docker instance."""
import argparse,json,logging
from .contract import Refusal,documents,texts,policy
from .preflight import resources
from .store import Store,rows_for

class InsertClient:
 ALLOWED={'has_collection','describe_collection','describe_index','get_load_state','query','search','create_schema','prepare_index_params','create_collection','flush'}
 def __init__(self,client,name):self.client,self.name,self.inserted=client,name,False
 def __getattr__(self,name):
  if name not in self.ALLOWED:raise Refusal('WRITE_OPERATION_REJECTED')
  def call(*args,**kwargs):
   if name not in {'create_schema','prepare_index_params'} and (not args or args[0]!=self.name):raise Refusal('COLLECTION_TARGET_REJECTED')
   return getattr(self.client,name)(*args,**kwargs)
  return call
 def insert_once(self,name,data,timeout):
  if name!=self.name or self.inserted or len(data)!=96:raise Refusal('SINGLE_INSERT_96_REQUIRED')
  self.inserted=True
  return self.client.insert(collection_name=name,data=data,timeout=timeout)

def inspect(client,p,docs,dtype):
 names=sorted(client.list_collections(timeout=5))
 if any(n!=p['collection'] for n in names):raise Refusal('FOREIGN_COLLECTIONS_RELEASE_INSTANCE_REQUIRED')
 if str(client.get_server_version(timeout=5)).removeprefix('v')!='2.5.26':raise Refusal('BGE_SERVER_VERSION')
 store=Store(InsertClient(client,p['collection']),dtype,p,docs)
 return store,{'collections':names,'target':store.inspect()}

def execute(client,dtype,encoder_factory,approve=False):
 # Approval is evaluated before any endpoint connection in main and again before encoding here.
 if approve is not True:raise Refusal('NEW_RELEASE_COLLECTION_APPROVAL_REQUIRED')
 p,docs=documents();store,before=inspect(client,p,docs,dtype)
 count=len(before['target']['existing_ids'])
 if count==96:return dict(store.verify(),inserted=0,encoding_executed=False)
 if count:raise Refusal('PARTIAL_COLLECTION_REQUIRES_REVIEW_NO_REPAIR')
 enc=encoder_factory('/models/bge');vectors,proof=enc.encode(texts(docs),'passage')
 if proof.get('real_embedding_inference') is not True:raise Refusal('REAL_EMBEDDINGS_REQUIRED')
 current,after=inspect(client,p,docs,dtype)
 if before!=after:raise Refusal('CONCURRENT_INVENTORY_CHANGE')
 result=current.ingest(rows_for(docs,vectors),allow_write=True)
 result.update(real_embedding_inference=True,independent_release_collection=True)
 return result

def arm_limits(p,resource_module=None,signal_module=None):
 import resource,signal
 resource_module=resource_module or resource;signal_module=signal_module or signal
 budget=p['budget']
 for key,name in [('address_space_bytes','RLIMIT_AS'),('cpu_s','RLIMIT_CPU'),('output_bytes','RLIMIT_FSIZE')]:
  value=budget[key];resource_module.setrlimit(getattr(resource_module,name),(value,value))
 def expired(*unused):raise Refusal('BGE_INDEX_RESOURCE_BUDGET_EXCEEDED')
 signal_module.signal(signal_module.SIGALRM,expired)
 signal_module.signal(signal_module.SIGXCPU,expired)
 signal_module.alarm(budget['wall_s'])
 return lambda:signal_module.alarm(0)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--approve-new-release-collection',action='store_true');a=parser.parse_args()
 if not a.approve_new_release_collection:raise Refusal('NEW_RELEASE_COLLECTION_APPROVAL_REQUIRED')
 res=resources()
 if res['available_memory_bytes'] is None or res['available_memory_bytes']<policy()['budget']['min_memory_free_bytes']:raise Refusal('BGE_MEMORY_HEADROOM')
 cancel_alarm=arm_limits(policy())
 from .encoder import Encoder
 from pymilvus import MilvusClient,DataType
 logging.getLogger('pymilvus').handlers=[logging.NullHandler()];logging.getLogger('pymilvus').propagate=False
 client=MilvusClient(uri='http://milvus:19530',db_name='default',timeout=5)
 try:print(json.dumps(execute(client,DataType,Encoder,True)))
 finally:client.close();cancel_alarm()
if __name__=='__main__':
 try:main()
 except Refusal as error:raise SystemExit(str(error) if __import__('re').fullmatch('[A-Z0-9_]{1,100}',str(error)) else 'INDEXING_REFUSED')
 except ImportError:raise SystemExit('BGE_DEPENDENCY_MISSING')
 except Exception:raise SystemExit('INDEXING_TECHNICAL_UNAVAILABLE_NO_RETRY')
