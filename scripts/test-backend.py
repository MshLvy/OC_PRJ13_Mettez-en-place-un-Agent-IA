#!/usr/bin/env python3
"""Run maintained backend tests offline in this checkout; never load private .env."""
import io,json,os,sys
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/validation';OUT.mkdir(parents=True,exist_ok=True)
# Drop inherited secret values before importing any application module.
os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',HOME=str(OUT),LANG='C.UTF-8',PYTHONDONTWRITEBYTECODE='1',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'backend')];os.chdir(ROOT/'backend')
counts={'network':0,'processes':0}
def audit(event,args):
 if event in ('socket.connect','subprocess.Popen'):
  counts['network' if event=='socket.connect' else 'processes']+=1;raise AssertionError('OFFLINE_TEST_ONLY')
sys.addaudithook(audit)
import pytest
out=io.StringIO();err=io.StringIO()
with redirect_stdout(out),redirect_stderr(err):code=pytest.main(['-q','-p','no:cacheprovider','--basetemp',str(OUT/'tmp'),*sys.argv[1:]])
(OUT/'backend.json').write_text(json.dumps({'exit_code':int(code),'output':out.getvalue(),'stderr':err.getvalue(),'guards':counts},indent=2)+'\n')
print(out.getvalue());print(json.dumps(counts));raise SystemExit(code)
