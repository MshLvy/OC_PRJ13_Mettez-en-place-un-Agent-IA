#!/usr/bin/env python3
"""Operator-only first configuration. Never print passwords or replace existing ones."""
from pathlib import Path
import os,re,secrets,subprocess
ROOT=Path(__file__).resolve().parents[1]
def configure(root=ROOT,volume_exists=None):
 if volume_exists is None:
  result=subprocess.run(['docker','--host=unix:///var/run/docker.sock','volume','ls','--filter','name=^p13-release_sessions-data$','--format','{{.Name}}'],check=True,text=True,stdout=subprocess.PIPE)
  volume_exists=bool(result.stdout.strip())
 if volume_exists:raise ValueError('EXISTING_MONGO_VOLUME_KEEP_CREDENTIALS')
 p=root/'.env';text=p.read_text()
 if re.search(r'(?m)^\s*(?:MONGO_PASSWORD|MONGO_ADMIN_PASSWORD)\s*=',text):raise ValueError('MONGO_PARAMETERS_EXIST_NO_REPLACEMENT')
 a=secrets.token_hex(32);b=secrets.token_hex(32)
 fd=os.open(p,os.O_WRONLY|os.O_APPEND)
 try:
  os.fchmod(fd,0o600);os.write(fd,('\nMONGO_PASSWORD='+a+'\nMONGO_ADMIN_PASSWORD='+b+'\n').encode())
 finally:os.close(fd)
 return 'NEW_MONGO_PRIVATE_PARAMETERS_CREATED_NO_VALUES_SHOWN'
if __name__=='__main__':
 try:print(configure())
 except Exception:raise SystemExit('MONGO_CONFIG_REFUSED: no credential displayed or replaced')
