"""Release packaging guards with synthetic embeddings and a nonpersistent SDK double."""
import copy,hashlib,json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from retrieval import acquire,contract,index,store

VECTOR=[1.]+[0.]*1023
class Type:
 VARCHAR='varchar';FLOAT_VECTOR='float_vector'
class Schema:
 def __init__(self,**kw):self.value=dict(kw,fields=[])
 def add_field(self,name,datatype,**kw):self.value['fields'].append(dict(name=name,type=datatype,params={k:str(v) for k,v in kw.items() if k!='is_primary'},is_primary=kw.get('is_primary',False)))
class Index:
 def add_index(self,**kw):pass
class SDK:
 def __init__(self):self.rows=[];self.names=[];self.schema=None;self.inserts=0;self.calls=[]
 def list_collections(self,**kw):self.calls.append('list');return list(self.names)
 def get_server_version(self,**kw):return '2.5.26'
 def has_collection(self,name,**kw):return name in self.names
 def create_schema(self,**kw):return Schema(**kw)
 def prepare_index_params(self):return Index()
 def create_collection(self,name,schema,index_params,**kw):self.names.append(name);self.schema=schema.value
 def describe_collection(self,name,**kw):return self.schema
 def describe_index(self,name,index,**kw):return dict(index_type='FLAT',metric_type='IP',field_name='embedding')
 def get_load_state(self,name,**kw):return {'state':3}
 def query(self,name,**kw):return copy.deepcopy(self.rows)
 def insert(self,collection_name,data,**kw):self.inserts+=1;self.rows=copy.deepcopy(data)
 def flush(self,name,**kw):pass
class Encoder:
 def __init__(self,path):pass
 def encode(self,texts,role):return [VECTOR for _ in texts],{'real_embedding_inference':True,'test_double':True}

def populated():
 c=SDK();index.execute(c,Type,Encoder,True);return c

def test_corpus_identity_and_release_target():
 p,docs=contract.documents()
 assert len(docs)==96 and p['collection']=='p13_openings_bge_1024_v1'
 assert len({r['chunk_id'] for r in docs})==96
 assert all(json.loads(d['payload_json'])['chunk']['human_review']=='pending' for d in docs)

def test_no_approval_no_endpoint_or_encoding():
 c=SDK();enc=Mock(side_effect=AssertionError('NO_ENCODING'))
 with pytest.raises(ValueError,match='APPROVAL'):index.execute(c,Type,enc,False)
 assert c.calls==[] and c.inserts==0;enc.assert_not_called()

def test_empty_dedicated_database_one_insert_96_vectors():
 c=SDK();r=index.execute(c,Type,Encoder,True)
 assert r['entities_verified']==96 and r['inserted']==96 and c.inserts==1
 assert r['independent_release_collection'] and len(c.rows)==96
 assert all(len(r['embedding'])==1024 for r in c.rows)

def test_rerun_full_collection_verifies_without_reencoding_or_writing():
 c=populated();enc=Mock(side_effect=AssertionError('NO_REEMBEDDING'))
 r=index.execute(c,Type,enc,True)
 assert r['inserted']==0 and not r['encoding_executed'] and c.inserts==1;enc.assert_not_called()

def test_unknown_collections_refused_before_encoding():
 c=SDK();c.names=['another_database_collection'];enc=Mock()
 with pytest.raises(ValueError,match='FOREIGN_COLLECTIONS'):index.execute(c,Type,enc,True)
 assert c.inserts==0;enc.assert_not_called()

def test_partial_collection_refused_without_repair():
 c=populated();c.rows=c.rows[:1];enc=Mock()
 with pytest.raises(ValueError,match='PARTIAL_COLLECTION'):index.execute(c,Type,enc,True)
 assert len(c.rows)==1 and c.inserts==1;enc.assert_not_called()

def test_actual_schema_change_refused():
 c=populated();c.schema['fields'][0]['params']['max_length']='1'
 with pytest.raises(ValueError,match='SCHEMA_CONFLICT'):index.execute(c,Type,Encoder,True)
 assert c.inserts==1

def test_vector_tampering_refused():
 c=populated();c.rows[0]['embedding']=[0.,1.]+[0.]*1022
 with pytest.raises(ValueError,match='VECTOR_DIGEST'):index.execute(c,Type,Encoder,True)
 assert c.inserts==1

def test_concurrent_creation_refused_without_insert():
 c=SDK()
 class Concurrent(Encoder):
  def encode(self,texts,role):
   c.names=['foreign_concurrent_collection'];return super().encode(texts,role)
 with pytest.raises(ValueError,match='FOREIGN_COLLECTIONS'):index.execute(c,Type,Concurrent,True)
 assert c.inserts==0

def test_synthetic_unproven_encoder_flag_cannot_create_collection():
 c=SDK();encoder=Mock();encoder.encode.return_value=([VECTOR]*96,{'real_embedding_inference':False})
 with pytest.raises(ValueError,match='REAL_EMBEDDINGS'):index.execute(c,Type,lambda _:encoder,True)
 assert not c.names and not c.inserts

@pytest.mark.parametrize('method',['drop_collection','delete','upsert','release_collection'])
def test_no_destructive_sdk_interface(method):
 wrapper=index.InsertClient(SDK(),'p13_openings_bge_1024_v1')
 with pytest.raises(ValueError,match='OPERATION_REJECTED'):getattr(wrapper,method)

def test_public_acquisition_needs_approval(tmp_path):
 opener=Mock(side_effect=AssertionError('NO_HTTP'))
 with pytest.raises(ValueError,match='APPROVAL'):acquire.acquire('model',tmp_path,False,opener)
 opener.assert_not_called()

def test_dependency_cache_hash_conflict_never_overwrites(tmp_path,monkeypatch):
 monkeypatch.setattr(acquire.shutil,'disk_usage',lambda _:SimpleNamespace(free=20*1024**3))
 monkeypatch.setattr(acquire,'rows',lambda _: [{'file':'unit.whl','url':'https://example.invalid/unit','sha256':'0'*64}])
 f=tmp_path/'unit.whl';f.write_bytes(b'synthetic-test-only')
 opener=Mock()
 with pytest.raises(ValueError,match='CONFLICT_NO_OVERWRITE'):acquire.acquire('dependencies',tmp_path,True,opener)
 assert f.read_bytes()==b'synthetic-test-only';opener.assert_not_called()

def test_existing_model_missing_file_has_explicit_diagnostic(tmp_path):
 from retrieval.preflight import verify_model
 with pytest.raises(ValueError,match='BGE_MODEL_FILE_MISSING'):verify_model(tmp_path)

def operations():
 import runpy
 from pathlib import Path
 return runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/p13'))

def test_stop_only_release_application_services(monkeypatch):
 op=operations();g=op['main'].__globals__;g['owner_guard']=lambda:True;g['run']=Mock()
 monkeypatch.setattr('sys.argv',['p13','stop']);op['main']()
 args=g['run'].call_args.args[0]
 assert 'p13-release' in args and args[-3:]==['stop','frontend','backend']
 assert '--host=unix:///var/run/docker.sock' in args
 assert not any(x in args for x in ['down','-v','prune','milvus','mongodb'])

def test_foreign_volume_labels_refused():
 op=operations();g=op['owner_guard'].__globals__;g['run']=Mock(side_effect=[SimpleNamespace(stdout='p13-release_milvus-data\n'),SimpleNamespace(stdout=json.dumps({'com.docker.compose.project':'another-project'}))])
 with pytest.raises(ValueError,match='OWNERSHIP_REFUSED'):op['owner_guard']()

def test_mongo_config_existing_volume_refused_before_file_read(tmp_path):
 import runpy
 from pathlib import Path
 mod=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/mongo-config.py'))
 with pytest.raises(ValueError,match='KEEP_CREDENTIALS'):mod['configure'](tmp_path,True)
 assert not (tmp_path/'.env').exists()

def test_mongo_config_existing_parameters_preserved(tmp_path):
 import runpy
 from pathlib import Path
 mod=runpy.run_path(str(Path(__file__).resolve().parents[2]/'scripts/mongo-config.py'))
 p=tmp_path/'.env';p.write_text('MONGO_PASSWORD=synthetic-unit-value\n')
 with pytest.raises(ValueError,match='NO_REPLACEMENT'):mod['configure'](tmp_path,False)
 assert p.read_text()=='MONGO_PASSWORD=synthetic-unit-value\n'

def test_default_example_end_to_end_without_keys_or_services(monkeypatch):
 from pathlib import Path
 from fastapi.testclient import TestClient
 from app.main import create_app
 from app.game import rebuild,snapshot
 root=Path(__file__).resolve().parents[2]
 for line in (root/'.env.example').read_text().splitlines():
  if line and not line.startswith('#'):
   key,value=line.split('=',1);monkeypatch.setenv(key,value)
 h=['e2e4','c7c5'];b,_=rebuild(h)
 with TestClient(create_app(),client=('127.0.0.1',50000)) as c:
  caps=c.get('/api/v1/demo/capabilities').json()
  assert caps['demo_enabled'] and caps['allowed_modes']==['simulation']
  r=c.post('/api/v1/demo/analysis',json={'history':h,'fen':b.fen(en_passant='fen'),'snapshot':snapshot(h),'revision':2,'demo_mode':'simulation'})
  assert r.status_code==200 and r.json()['simulation']
  assert 'analysis.execute_action' in r.headers['X-Workflow-Path']
  r=c.post('/api/v1/advisor/conversation',json={'history':h,'fen':b.fen(en_passant='fen'),'question':'Pourquoi le pion c5 contrôle d4 dans la Sicilienne ?','request_generation':True,'demo_mode':'simulation'})
  assert r.status_code==200 and r.json()['passages'] and r.json()['generation']['status']=='deterministic'
  assert 'rag.execute_action' in r.headers['X-Workflow-Path']
  r=c.post('/api/v1/videos/explore',json={'action':'explore_videos','opening':'sicilienne','fen':b.fen(en_passant='fen'),'history':h,'language':'fr'})
  assert r.status_code==200 and r.json()['source_mode']=='disabled'
  assert 'videos.execute_action' in r.headers['X-Workflow-Path']
  r=c.get('/api/v1/sessions')
  assert r.status_code==503 and 'sessions.execute_action' in r.headers['X-Workflow-Path']


def test_index_cpu_memory_output_and_wall_budgets_are_armed_with_doubles():
 r=SimpleNamespace(RLIMIT_AS=1,RLIMIT_CPU=2,RLIMIT_FSIZE=3,setrlimit=Mock())
 s=SimpleNamespace(SIGALRM=14,SIGXCPU=24,signal=Mock(),alarm=Mock())
 cancel=index.arm_limits(contract.policy(),r,s)
 assert r.setrlimit.call_args_list[0].args==(1,(8589934592,8589934592))
 assert r.setrlimit.call_args_list[1].args==(2,(1700,1700))
 assert r.setrlimit.call_args_list[2].args==(3,(8388608,8388608))
 s.alarm.assert_called_once_with(1800);cancel();assert s.alarm.call_args.args==(0,)

def test_index_budget_signal_refuses_without_private_diagnostic():
 r=SimpleNamespace(RLIMIT_AS=1,RLIMIT_CPU=2,RLIMIT_FSIZE=3,setrlimit=Mock())
 s=SimpleNamespace(SIGALRM=14,SIGXCPU=24,signal=Mock(),alarm=Mock())
 index.arm_limits(contract.policy(),r,s)
 with pytest.raises(ValueError,match='BGE_INDEX_RESOURCE_BUDGET_EXCEEDED'):
  s.signal.call_args_list[0].args[1](0,None)
