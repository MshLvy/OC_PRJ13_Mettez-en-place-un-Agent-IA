"""Explicit, bounded public acquisition; no API keys, retries or automatic model download."""
import argparse,hashlib,json,shutil,time,urllib.request
from pathlib import Path
from .contract import Refusal,HERE,policy

def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def rows(kind):return json.loads((HERE/('model-files.json' if kind=='model' else 'artifacts.json')).read_text())['files' if kind=='model' else 'artifacts']
def verify_dependencies(folder):
 folder=Path(folder);expected=rows('dependencies')
 if folder.is_symlink() or not folder.is_dir() or {p.name for p in folder.iterdir()}!={r['file'] for r in expected}:raise Refusal('DEPENDENCY_BUNDLE_FILE_SET')
 for row in expected:
  f=folder/row['file']
  if f.is_symlink() or sha(f)!=row['sha256']:raise Refusal('DEPENDENCY_BUNDLE_SHA')
 return {'verified_dependency_artifacts':len(expected)}
def acquire(kind,folder,approve=False,opener=urllib.request.urlopen):
 if approve is not True:raise Refusal('PUBLIC_DOWNLOAD_APPROVAL_REQUIRED')
 folder=Path(folder)
 if folder.is_symlink():raise Refusal('CACHE_SYMLINK_REJECTED')
 folder.mkdir(parents=True,exist_ok=True)
 required=12*1024**3 if kind=='model' else 3*1024**3
 if shutil.disk_usage(folder).free<required:raise Refusal('ACQUISITION_DISK_HEADROOM')
 limit=2350000000 if kind=='model' else 1200000000;received=0;start=time.monotonic();verified=0
 for row in rows(kind):
  name=row['file']
  if Path(name).name!=name:raise Refusal('MANIFEST_PATH_REJECTED')
  dest=folder/name
  if dest.is_symlink():raise Refusal('CACHE_SYMLINK_REJECTED')
  if dest.exists():
   if sha(dest)!=row['sha256']:raise Refusal('EXISTING_ARTIFACT_CONFLICT_NO_OVERWRITE')
   verified+=1;continue
  part=folder/(name+'.part')
  if part.exists():raise Refusal('PARTIAL_ARTIFACT_REQUIRES_OPERATOR_REVIEW')
  h=hashlib.sha256();count=0
  with opener(row['url'],timeout=30) as src,part.open('xb') as out:
   if not src.geturl().startswith('https://'):raise Refusal('HTTPS_REQUIRED')
   while True:
    b=src.read(1024*1024)
    if not b:break
    count+=len(b);received+=len(b)
    if received>limit or count>row.get('bytes',300000000) or time.monotonic()-start>1800:raise Refusal('ACQUISITION_BUDGET')
    h.update(b);out.write(b)
  if h.hexdigest()!=row['sha256'] or ('bytes' in row and count!=row['bytes']):raise Refusal('ACQUISITION_SHA_OR_SIZE')
  # No overwrite even if another process acquired the destination meanwhile.
  import os
  os.link(part,dest);part.unlink();verified+=1
 return {'verified':verified,'downloaded_bytes':received,'model_inference':False}
def main():
 p=argparse.ArgumentParser();p.add_argument('--kind',choices=['model','dependencies']);p.add_argument('--directory',type=Path);p.add_argument('--approve-public-downloads',action='store_true');p.add_argument('--verify-dependencies',type=Path);a=p.parse_args()
 if a.verify_dependencies:result=verify_dependencies(a.verify_dependencies)
 else:
  if not a.kind or not a.directory:p.error('kind and directory required')
  result=acquire(a.kind,a.directory,a.approve_public_downloads)
 print(json.dumps(result))
if __name__=='__main__':
 try:main()
 except Refusal as error:raise SystemExit(str(error) if __import__('re').fullmatch('[A-Z0-9_]{1,100}',str(error)) else 'ACQUISITION_REFUSED')
 except (OSError,ValueError):raise SystemExit('ACQUISITION_TECHNICAL_UNAVAILABLE_NO_RETRY')
