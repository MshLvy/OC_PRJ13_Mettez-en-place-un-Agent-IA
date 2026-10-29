"""Pinned original BGE-M3 CPU FP32, CLS/L2. No remote or sparse/multivector path."""
import importlib,time
from .contract import policy,Refusal
from .preflight import verify_model,versions
class Encoder:
    def __init__(self,path):
        start=time.monotonic();self.proof=verify_model(path)
        if versions()!=policy()['dependencies']:raise Refusal('BGE_DEPENDENCY_VERSIONS')
        t=importlib.import_module('torch');tr=importlib.import_module('transformers');importlib.import_module('accelerate')
        self.t=t;t.set_num_threads(1);t.set_num_interop_threads(1);t.manual_seed(0);t.use_deterministic_algorithms(True)
        self.tokenizer=tr.AutoTokenizer.from_pretrained(str(path),local_files_only=True,trust_remote_code=False)
        self.model=tr.AutoModel.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,use_safetensors=False,torch_dtype=t.float32,low_cpu_mem_usage=True,device_map={'':'cpu'}).eval()
        c=self.model.config
        if c.model_type!='xlm-roberta' or c.hidden_size!=1024 or c.num_hidden_layers!=24 or any(p.device.type!='cpu' or p.dtype!=t.float32 for p in self.model.parameters()):raise Refusal('BGE_ARCHITECTURE_OR_DTYPE')
        self.cold_load_hash_s=time.monotonic()-start
    def encode(self,texts,role):
        if role not in ('query','passage') or not 1<=len(texts)<=96 or any(not isinstance(x,str) or not x.strip() or len(x)>6000 for x in texts):raise Refusal('BGE_INPUT_BUDGET')
        counts=[len(x) for x in self.tokenizer(texts,truncation=False)['input_ids']]
        if max(counts)>512:raise Refusal('BGE_TOKENS_OVER_512_NO_TRUNCATION')
        start=time.monotonic();out=[];t=self.t
        for text in texts:
            batch=self.tokenizer([text],padding=True,truncation=False,return_tensors='pt')
            with t.inference_mode():
                v=self.model(**batch).last_hidden_state[:,0];norm=v.norm(p=2,dim=1,keepdim=True)
                if not t.isfinite(v).all() or (norm<=0).any():raise Refusal('BGE_NONFINITE_OR_ZERO_CLS')
                out.extend((v/norm).tolist())
        return out,{'real_embedding_inference':True,'model_proof':self.proof,'tokens':counts,'truncated':0,'role':role,'prefix':None,'pooling':'CLS+L2','seconds':time.monotonic()-start,'cold_load_hash_s':self.cold_load_hash_s}
