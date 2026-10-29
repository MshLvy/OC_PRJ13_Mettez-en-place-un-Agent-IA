import hashlib,importlib.metadata,json,os,re,shutil,zipfile
from pathlib import Path
from .contract import ROOT,policy,Refusal

def resources():
 diag={};diagnostics=[]
 for label,file in [('memory_max','/sys/fs/cgroup/memory.max'),('memory_current','/sys/fs/cgroup/memory.current'),('cpu_max','/sys/fs/cgroup/cpu.max')]:
  try:diag[label]=Path(file).read_text().strip()
  except (OSError,UnicodeError) as error:
   diag[label]=None;diagnostics.append({'interface':file,'status':'missing' if isinstance(error,FileNotFoundError) else 'unreadable','error_type':type(error).__name__})
 try:
  mem=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
 except (OSError,StopIteration,ValueError):mem=None
 if diag['memory_max'] and diag['memory_max'].isdigit() and diag['memory_current'] and diag['memory_current'].isdigit():
  left=max(0,int(diag['memory_max'])-int(diag['memory_current']));mem=min(mem,left) if mem is not None else left
 return {'disk_free_bytes':shutil.disk_usage(ROOT).free,'available_memory_bytes':mem,'cgroup':diag,'cgroup_diagnostics':diagnostics,'unknown_limits_are_not_capacity':True}

def manifest():
    raw=(Path(__file__).with_name('model-files.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=policy()['bge_manifest_sha256']:raise Refusal('BGE_MANIFEST_DRIFT')
    return json.loads(raw)
def verify_model(folder):
    p=Path(folder);m=manifest();names={r['file'] for r in m['files']}
    if p.is_symlink():raise Refusal('BGE_MODEL_SYMLINK')
    if not p.is_dir():raise Refusal('BGE_MODEL_DIRECTORY_MISSING')
    if any(not (p/n).exists() for n in names):raise Refusal('BGE_MODEL_FILE_MISSING')
    if {f.name for f in p.iterdir() if f.is_file() and f.suffix in ('.json','.bin','.model','.safetensors')}!=names:raise Refusal('BGE_MODEL_FILE_SET')
    for row in m['files']:
        f=p/row['file'];h=hashlib.sha256()
        if f.is_symlink() or not f.is_file() or f.stat().st_size!=row['bytes']:raise Refusal('BGE_MODEL_SIZE_OR_SYMLINK')
        with f.open('rb') as src:
            for b in iter(lambda:src.read(1024*1024),b''):h.update(b)
        if h.hexdigest()!=row['sha256']:raise Refusal('BGE_MODEL_SHA')
    if not zipfile.is_zipfile(p/'pytorch_model.bin'):raise Refusal('BGE_ZIP_REQUIRED')
    return {'model':m['model'],'revision':m['revision'],'files_verified':6,'manifest_sha256':policy()['bge_manifest_sha256']}

def versions():
    result={}
    for n in policy()['dependencies']:
        try:result[n]=importlib.metadata.version(n)
        except importlib.metadata.PackageNotFoundError:result[n]=None
    return result
