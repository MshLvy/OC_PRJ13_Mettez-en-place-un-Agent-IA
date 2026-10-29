"""Self-contained release corpus/policy identity. No experimental evaluation inputs."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
POLICY_SHA='30d5673ccacd28f579a39532d16459d52df91355b7a59bce23a668b2ac3676b2'
class Refusal(ValueError):pass
def canonical(v):return json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def digest(v):return hashlib.sha256(canonical(v).encode()).hexdigest()
def policy():
 raw=(HERE/'policy.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=POLICY_SHA:raise Refusal('BGE_SIGNED_CONTRACT_DRIFT')
 return json.loads(raw)
def documents():
 p=policy();path=ROOT/'backend/app/data/advisor_v3/chunks.json'
 if path.is_symlink() or path.stat().st_size>1024*1024:raise Refusal('BGE_CORPUS_IDENTITY')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=p['corpus_manifest_sha256']:raise Refusal('BGE_CORPUS_IDENTITY')
 chunks=json.loads(raw)
 if len(chunks)!=96 or len({c['chunk_id'] for c in chunks})!=96:raise Refusal('BGE_CORPUS_IDENTITY')
 docs=[]
 for c in chunks:
  if c['licence']!='CC-BY-SA-4.0' or c['human_review']!='pending' or c['production_approved'] is not False or not c['source_citations'] or hashlib.sha256(c['text'].encode()).hexdigest()!=c['text_sha256']:raise Refusal('BGE_CORPUS_IDENTITY')
  payload={'chunk':c,'experimental_status':'experimental_not_expert_validated','policy_sha256':digest(p),'corpus_manifest_sha256':p['corpus_manifest_sha256'],'model_contract':p['model']}
  text=canonical(payload)
  if len(text.encode())>65535:raise Refusal('BGE_PAYLOAD_BUDGET')
  docs.append({'chunk_id':c['chunk_id'],'text_sha256':c['text_sha256'],'corpus_sha256':p['corpus_manifest_sha256'],'policy_sha256':digest(p),'model_sha256':digest(p['model']),'payload_json':text,'payload_sha256':hashlib.sha256(text.encode()).hexdigest()})
 return p,docs
def texts(docs):return [json.loads(d['payload_json'])['chunk']['text'] for d in docs]
