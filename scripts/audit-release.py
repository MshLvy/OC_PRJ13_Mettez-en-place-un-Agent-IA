#!/usr/bin/env python3
"""Read selected public files only; local audit, no provider/network or private .env read."""
import ast,hashlib,json,os,re,subprocess,sys
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1]
IGNORED={'.git','work','node_modules','.venv','venv','models','wheelhouse','.pytest_cache','__pycache__','dist'}
OUTPUTS={'validation/audit.json','validation/files.json'}
def selected():
 out=[]
 for current,dirs,files in os.walk(ROOT,followlinks=False):
  for d in list(dirs):
   p=Path(current)/d
   if d in IGNORED:dirs.remove(d)
   elif p.is_symlink():raise ValueError('SYMLINK_DIRECTORY_NOT_PUBLISHABLE')
  for name in files:
   p=Path(current)/name;rel=p.relative_to(ROOT).as_posix()
   if name.startswith('.env') and name!='.env.example':continue # never open a private config
   if rel in OUTPUTS:continue
   if p.is_symlink():raise ValueError('SYMLINK_FILE_NOT_PUBLISHABLE')
   if p.suffix.lower() in {'.bin','.gguf','.safetensors','.whl','.zip','.pyc','.pem','.key'}:raise ValueError('WEIGHT_CACHE_OR_SECRET_FILE_REJECTED')
   if p.stat().st_size>5*1024*1024:raise ValueError('UNEXPECTED_LARGE_PUBLIC_FILE')
   out.append(p)
 return sorted(out)
def main():
 results=[];files=selected()
 def record(name,ok,detail):results.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
 findings=[];badlinks=[];links=0;python=0
 patterns=[r'\blip_[A-Za-z0-9_-]{16,}\b',r'\b(?:gsk_|sk-)[A-Za-z0-9_-]{20,}\b',r'\bAIza[A-Za-z0-9_-]{30,}\b',r'\bgh[pousr]_[A-Za-z0-9]{25,}\b',r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY',r'mongodb(?:\+srv)?://[^\s/@]+:[^\s/@]+@']
 references=[]
 for p in files:
  rel=p.relative_to(ROOT).as_posix();b=p.read_bytes()
  if p.suffix=='.png':continue
  try:text=b.decode('utf-8')
  except UnicodeError:findings.append({'path':rel,'category':'unexpected_binary'});continue
  for line_no,line in enumerate(text.splitlines(),1):
   # Pattern expressions in this scanner are not secret literals.
   if rel!='scripts/audit-release.py' and any(re.search(pattern,line) for pattern in patterns):findings.append({'path':rel,'line':line_no,'category':'credential_shape_requires_review'})
   if rel!='scripts/audit-release.py' and re.search(r'OC_PRJ13[^\s/]*_DEV|reports/codex|handoffs/|/workspace/|/mnt/[a-z]/Users/',line):references.append({'path':rel,'line':line_no})
  if p.suffix=='.md':
   if text.count('```')%2:badlinks.append({'path':rel,'category':'unclosed_fence'})
   for match in re.finditer(r'!?\[[^\]\n]*\]\(([^\s)]+)\)',text):
    target=match.group(1).strip('<>');url=urlsplit(target)
    if url.scheme or target.startswith('#'):continue
    dest=(p.parent/unquote(url.path)).resolve()
    if not dest.is_relative_to(ROOT) or not dest.exists():badlinks.append({'path':rel,'target':target})
    links+=1
  if p.suffix=='.py':ast.parse(text,filename=rel);python+=1
 record('public_files_secret_shapes',not findings,findings)
 record('no_private_or_internal_references',not references,references)
 record('markdown_links_and_fences',not badlinks,{'links':links,'issues':badlinks,'remote_urls':'not fetched','anchors':'not exhaustive'})
 record('python_sources_parse',True,{'modules':python})
 chunks=ROOT/'backend/app/data/advisor_v3/chunks.json';rows=json.loads(chunks.read_bytes())
 expected='7eb6b10749b1d09985139cb4fa89a5f2b11d75aa4ae2499e4614937923f86064'
 ok=hashlib.sha256(chunks.read_bytes()).hexdigest()==expected and len(rows)==len({r['chunk_id'] for r in rows})==96 and all(r['licence']=='CC-BY-SA-4.0' and r['human_review']=='pending' and r['source_citations'] for r in rows)
 record('corpus_identity_rights_metadata',ok,{'count':len(rows),'sha256':expected,'human_expert_validation':False})
 record('original_code_license_and_notices', 'Identifiant SPDX : GPL-3.0-or-later' in (ROOT/'LICENSE.md').read_text() and 'Version 3, 29 June 2007' in (ROOT/'LICENSES/GPL-3.0-or-later.txt').read_text() and (ROOT/'backend/app/data/openings/upstream/COPYING.txt').is_file(), {'original_code':'GPL-3.0-or-later','corpus':'CC-BY-SA-4.0','catalogue':'CC0-1.0'})
 record('excluded_experiments_and_private_data',not any((ROOT/x).exists() for x in ['reports','handoffs','evaluation','corpus']),{'old_corpora_or_evaluation_directories':False,'private_config_contents_read':False})
 def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True,stderr=subprocess.DEVNULL).strip()
 branch=git('branch','--show-current');count=int(git('rev-list','--all','--count') or '0');remotes=git('remote').splitlines()
 staged=git('ls-files','--cached').splitlines();badstage=[p for p in staged if p.startswith(('.env','models/','work/','wheelhouse/')) and p!='.env.example']
 # No imported alternate/shared source object database.
 gitdir=ROOT/'.git';independent=gitdir.is_dir() and not (gitdir/'objects/info/alternates').exists() and not (gitdir/'commondir').exists()
 record('new_main_repository_no_imported_history',branch=='main' and independent and not badstage,{'branch':branch,'commits':count,'remotes':remotes,'independent_objects':independent,'unsafe_staged_paths':badstage})
 metadata=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
 canonical=json.dumps(metadata,sort_keys=True,separators=(',',':')).encode();tree=hashlib.sha256(canonical).hexdigest()
 out=ROOT/'validation';out.mkdir(exist_ok=True)
 (out/'files.json').write_text(json.dumps({'files':metadata,'candidate_manifest_sha256':tree,'excluded_outputs':sorted(OUTPUTS)},ensure_ascii=False,indent=2)+'\n')
 summary={'date':'2026-10-29','checks':results,'passed':sum(x['status']=='PASS' for x in results),'failed':sum(x['status']=='FAIL' for x in results),'files':len(files),'candidate_manifest_sha256':tree,'provider_calls':0,'physical_clean_install_validated':False,'license_original_code':'GPL-3.0-or-later','public_push_performed':False}
 (out/'audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 for r in results:print(r['status'],r['name'],json.dumps(r['detail'],ensure_ascii=False))
 print('CANDIDATE_MANIFEST_SHA256',tree)
 return bool(summary['failed'])
if __name__=='__main__':raise SystemExit(main())
