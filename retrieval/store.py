"""Insert-only dedicated collection. No upsert/delete/drop/reset interface."""
import hashlib,json,math,struct
from .contract import Refusal,policy
FIELDS={'chunk_id':192,'text_sha256':64,'corpus_sha256':64,'policy_sha256':64,'model_sha256':64,'payload_sha256':64,'vector_sha256':64,'payload_json':65535}
INDEX='embedding_idx'
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def vector(v):
 if not isinstance(v,(list,tuple)) or len(v)!=1024 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):raise Refusal('FINITE_1024_VECTOR_REQUIRED')
 try:out=list(struct.unpack('!1024f',struct.pack('!1024f',*v)))
 except (OverflowError,struct.error):raise Refusal('FLOAT32_VECTOR_REQUIRED') from None
 if not all(math.isfinite(x) for x in out) or abs(sum(x*x for x in out)-1)>1e-4:raise Refusal('UNIT_VECTOR_REQUIRED')
 return out
def vector_sha(v):return hashlib.sha256(struct.pack('!1024f',*vector(v))).hexdigest()
def rows_for(docs,vectors):
 if len(docs)!=96 or len(vectors)!=96 or len({r['chunk_id'] for r in docs})!=96:raise Refusal('EXPECTED_96_IDENTITIES')
 return [dict(d,embedding=vector(v),vector_sha256=vector_sha(v)) for d,v in zip(docs,vectors)]
def marker(p):return 'p13|release_bge_v1|'+p['corpus_manifest_sha256']+'|'+digest(p)

def read_hit(hit):
 # Both MilvusClient dict and real PyMilvus Hit named primary key.
 try:
  ident=hit['chunk_id'];score=float(hit['distance']);entity=dict(hit.get('entity',{}))
 except (KeyError,TypeError,ValueError,AttributeError):raise Refusal('MILVUS_HIT_FORMAT') from None
 if not isinstance(ident,str) or not math.isfinite(score):raise Refusal('MILVUS_HIT_VALUES')
 entity.setdefault('chunk_id',ident);return ident,score,entity

class Store:
 def __init__(self,client,dtype,p,docs):
  if p!=policy():raise Refusal('BGE_POLICY_OR_TARGET_CONFLICT')
  if len(docs)!=96 or len({d['chunk_id'] for d in docs})!=96 or any(d['policy_sha256']!=digest(p) or d['model_sha256']!=digest(p['model']) or d['corpus_sha256']!=p['corpus_manifest_sha256'] or d['payload_sha256']!=hashlib.sha256(d['payload_json'].encode()).hexdigest() or json.loads(d['payload_json'])['model_contract']!=p['model'] for d in docs):raise Refusal('BGE_DOCUMENT_IDENTITY_CONFLICT')
  self.client,self.dtype,self.p,self.docs=client,dtype,p,docs;self.name=p['collection'];self.by={d['chunk_id']:d for d in docs}
 def validate(self):
  d=self.client.describe_collection(self.name,timeout=5);fields={f['name']:f for f in d.get('fields',[])}
  if d.get('description')!=marker(self.p) or d.get('auto_id') or d.get('enable_dynamic_field') or set(fields)!=set(FIELDS)|{'embedding'}:raise Refusal('COLLECTION_OWNERSHIP_OR_SCHEMA_CONFLICT')
  for name,length in FIELDS.items():
   f=fields[name]
   if f.get('type')!=self.dtype.VARCHAR or int(f.get('params',{}).get('max_length',0))!=length or bool(f.get('is_primary',False))!=(name=='chunk_id'):raise Refusal('FIELD_SCHEMA_CONFLICT')
  f=fields['embedding']
  if f.get('type')!=self.dtype.FLOAT_VECTOR or int(f.get('params',{}).get('dim',0))!=1024:raise Refusal('VECTOR_SCHEMA_CONFLICT')
  idx=self.client.describe_index(self.name,INDEX,timeout=5)
  if idx.get('index_type')!='FLAT' or idx.get('metric_type')!='IP' or idx.get('field_name','embedding')!='embedding':raise Refusal('INDEX_CONFLICT')
 def loaded(self):
  state=self.client.get_load_state(self.name,timeout=5).get('state')
  if not (state==3 or str(state) in ('Loaded','LoadState.Loaded')):raise Refusal('DEVELOPMENT_COLLECTION_NOT_LOADED')
 def actual(self):
  self.loaded();rows=self.client.query(self.name,filter='',limit=97,output_fields=[*FIELDS,'embedding'],consistency_level='Strong',timeout=15)
  if len(rows)>96 or len({r['chunk_id'] for r in rows})!=len(rows):raise Refusal('ROW_COUNT_CONFLICT')
  for row in rows:
   wanted=self.by.get(row.get('chunk_id'))
   if wanted is None or any(row.get(k)!=v for k,v in wanted.items()):raise Refusal('SAME_ID_CONTENT_OR_FOREIGN_ROW_CONFLICT')
   if row.get('vector_sha256')!=vector_sha(row.get('embedding')):raise Refusal('STORED_VECTOR_DIGEST_CONFLICT')
  return rows
 def inspect(self):
  if not self.client.has_collection(self.name,timeout=5):return {'collection_exists':False,'existing_ids':[],'missing_ids':sorted(self.by),'mutations':0}
  self.validate();rows=self.actual();ids={r['chunk_id'] for r in rows}
  return {'collection_exists':True,'existing_ids':sorted(ids),'missing_ids':sorted(self.by.keys()-ids),'mutations':0}
 def ingest(self,rows,allow_write=False):
  if allow_write is not True:raise Refusal('OPERATOR_WRITE_OPT_IN_REQUIRED')
  expected=rows_for(self.docs,[r['embedding'] for r in rows])
  if rows!=expected:raise Refusal('INGEST_ROWS_MUST_MATCH_SIGNED_ORDER_AND_VECTORS')
  state=self.inspect();created=False
  if not state['collection_exists']:
   schema=self.client.create_schema(auto_id=False,enable_dynamic_field=False,description=marker(self.p))
   for name,length in FIELDS.items():schema.add_field(name,self.dtype.VARCHAR,max_length=length,is_primary=name=='chunk_id')
   schema.add_field('embedding',self.dtype.FLOAT_VECTOR,dim=1024)
   index=self.client.prepare_index_params();index.add_index(field_name='embedding',index_name=INDEX,index_type='FLAT',metric_type='IP')
   # create_collection fails on a racing creator; no retry, overwrite or alternate name.
   self.client.create_collection(self.name,schema=schema,index_params=index,timeout=30);created=True
   self.validate();self.loaded()
  actual=self.actual();actual_by={r['chunk_id']:r for r in actual}
  for r in rows:
   if r['chunk_id'] in actual_by and any(actual_by[r['chunk_id']].get(k)!=v for k,v in r.items()):raise Refusal('EXISTING_VECTOR_RECOMPUTATION_CONFLICT')
  missing=[r for r in rows if r['chunk_id'] not in actual_by]
  if missing:
   self.client.insert_once(self.name,missing,timeout=30);self.client.flush(self.name,timeout=30)
  final=self.actual()
  if len(final)!=96:raise Refusal('POST_INSERT_INCOMPLETE_RERUN_REQUIRES_INSPECTION')
  for row in final:
   if row['vector_sha256']!=next(r['vector_sha256'] for r in rows if r['chunk_id']==row['chunk_id']):raise Refusal('POST_INSERT_VECTOR_CONFLICT')
  return {'created':created,'inserted':len(missing),'entities_verified':96,'idempotent_noop':not missing,'collection':self.name,'vector_artifact_sha256':digest(sorted((r['chunk_id'],r['vector_sha256']) for r in final))}
 def verify(self):
  state=self.inspect()
  if state['missing_ids']:raise Refusal('COLLECTION_INCOMPLETE')
  return {'entities_verified':96,'metadata_and_vector_digests_verified':True,'independent_reembedding_performed':False,'collection':self.name}
 def search(self,v,k=3):
  if type(k) is not int or not 1<=k<=3:raise Refusal('TOPK_BUDGET')
  self.verify();out=self.client.search(self.name,[vector(v)],anns_field='embedding',limit=k,search_params={'metric_type':'IP'},output_fields=list(FIELDS),consistency_level='Strong',timeout=15)
  if len(out)!=1 or len(out[0])>k:raise Refusal('SEARCH_SHAPE')
  hits=[];seen=set()
  for hit in out[0]:
   ident,score,row=read_hit(hit);expected=self.by.get(ident)
   if expected is None or ident in seen or any(row.get(k)!=v for k,v in expected.items()):raise Refusal('SEARCH_PROVENANCE_CONFLICT')
   if not -1.0001<=score<=1.0001:raise Refusal('IP_UNIT_SCORE_BOUNDS')
   seen.add(ident);hits.append((ident,score))
  return hits
