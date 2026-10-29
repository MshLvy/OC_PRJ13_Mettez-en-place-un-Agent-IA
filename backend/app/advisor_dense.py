"""Option Milvus E5 en lecture seule, isolée et jamais chargée au boot."""
from dataclasses import dataclass
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from app.advisor_data import ROOT

COLLECTION = 'opening_pilot_e5_384_v1'
REVISION = '614241f622f53c4eeff9890bdc4f31cfecc418b3'
TIMEOUT = 20
MAX_OUTPUT = 262144


class DenseError(ValueError):
    pass


@dataclass(frozen=True)
class DenseSettings:
    allowed: bool = False
    owner_confirmed: bool = False
    uri: str = ''
    model_dir: str = ''

    @classmethod
    def from_env(cls):
        def flag(name):
            v = os.getenv(name, 'false')
            if v not in ('true', 'false'):raise ValueError('INVALID_' + name)
            return v == 'true'
        result = cls(flag('ADVISOR_ALLOW_DENSE'), flag('ADVISOR_MILVUS_OWNER_CONFIRMED'),
                     os.getenv('ADVISOR_MILVUS_URI', ''), os.getenv('ADVISOR_E5_MODEL_DIR', ''))
        if result.uri:
            p = urlparse(result.uri)
            try:valid_port = p.port == 19530
            except ValueError:valid_port = False
            if (p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost', 'milvus') or not valid_port
                    or p.username or p.password or p.path not in ('', '/') or p.query or p.fragment):
                raise ValueError('ADVISOR_LOCAL_MILVUS_URI_REQUIRED')
        if result.model_dir and (not Path(result.model_dir).is_absolute() or len(result.model_dir) > 4096
                                 or any(ord(c) < 32 for c in result.model_dir)):
            raise ValueError('INVALID_ADVISOR_MODEL_PATH')
        return result


def readiness(settings):
    # Présence seulement, pas import de torch, hash des poids ou connexion.
    if not settings.allowed:return ['DENSE_NOT_AUTHORIZED']
    reasons = []
    if not settings.owner_confirmed:reasons.append('MILVUS_OWNERSHIP_NOT_CONFIRMED')
    if not settings.uri:reasons.append('MILVUS_ENDPOINT_NOT_CONFIGURED')
    if not settings.model_dir or not Path(settings.model_dir).is_dir():reasons.append('E5_LOCAL_MODEL_MISSING')
    if any(importlib.util.find_spec(n) is None for n in ('torch', 'transformers', 'pymilvus')):
        reasons.append('DENSE_DEPENDENCIES_MISSING')
    return reasons


class DenseRunner:
    evidence_kind = 'real_milvus'

    def __init__(self, settings):
        self.settings = settings
        self.quarantined = False
        self.last_worker_started = False

    def search(self, question):
        self.last_worker_started = False
        if self.quarantined:raise DenseError('DENSE_WORKER_QUARANTINED')
        reasons = readiness(self.settings)
        if reasons:raise DenseError(reasons[0])
        env = {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
               'PYTHONPATH': str(ROOT / 'backend') + os.pathsep + str(ROOT),
               'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
               'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}
        payload = json.dumps({'question': question, 'uri': self.settings.uri, 'model_dir': self.settings.model_dir})
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen([sys.executable, '-m', 'app.advisor_dense_worker'], stdin=subprocess.PIPE,
                stdout=out, stderr=err, env=env, start_new_session=True)
            self.last_worker_started = True
            try:
                proc.communicate(payload.encode(), timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                try:os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:pass
                try:proc.wait(timeout=2)
                except subprocess.TimeoutExpired:self.quarantined = True
                raise DenseError('DENSE_WORKER_TIMEOUT') from None
            if proc.returncode != 0:raise DenseError('DENSE_WORKER_FAILED')
            if out.tell() > MAX_OUTPUT or err.tell() > MAX_OUTPUT:raise DenseError('DENSE_OUTPUT_LIMIT')
            out.seek(0)
            try:data = json.loads(out.read(MAX_OUTPUT + 1))
            except (ValueError, UnicodeError):raise DenseError('DENSE_OUTPUT_INVALID') from None
        if data.get('status') != 'ok':
            code = data.get('code', '')
            raise DenseError(code if isinstance(code, str) and code in (
                'MILVUS_IDENTITY_MISMATCH', 'DENSE_RESOURCE_LIMIT', 'MILVUS_NOT_AVAILABLE',
                'E5_MODEL_OR_ENCODING_UNAVAILABLE') else 'DENSE_UNAVAILABLE')
        if (data.get('kind') != 'REAL_E5_MILVUS_READ_ONLY' or data.get('collection') != COLLECTION
                or data.get('model_revision') != REVISION or not data.get('metadata_verified')
                or not isinstance(data.get('hits'), list) or len(data['hits']) > 24):
            raise DenseError('DENSE_OUTPUT_IDENTITY')
        ids = set()
        for h in data['hits']:
            if (not isinstance(h, dict) or not isinstance(h.get('chunk_id'), str) or h['chunk_id'] in ids
                    or type(h.get('score')) not in (float, int) or not math.isfinite(h['score']) or not -1.001 <= h['score'] <= 1.001):
                raise DenseError('DENSE_OUTPUT_INVALID')
            ids.add(h['chunk_id'])
        return data
