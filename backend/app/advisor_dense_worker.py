"""Worker E5/Milvus optionnel : aucune ingestion, création, charge ou suppression."""
import json
import math
import sys
import time


def perform(payload, *, search=None, encoder_factory=None, connector=None):
    simulated = any(v is not None for v in (search, encoder_factory, connector))
    # Imports lourds seulement après activation serveur et précontrôle parent.
    from app.advisor_data import load_search, legacy_modules
    legacy_modules()
    from tools.e5 import store as store_module
    from tools.e5.encoder import Encoder
    from app.advisor_dense import COLLECTION, REVISION
    search = search or load_search()
    connector = connector or store_module.connect
    encoder_factory = encoder_factory or Encoder
    client = None
    stage = 'connect'
    try:
        started = time.monotonic()
        store = connector(payload['uri']);client = store.client
        stage = 'metadata'
        store_module.check_schema(client.describe_collection(COLLECTION, timeout=3), store.dtype)
        index = client.describe_index(COLLECTION, 'embedding', timeout=3)
        if index.get('metric_type') != 'IP' or index.get('index_type') != 'FLAT':
            raise ValueError('IDENTITY')
        actual = client.query(COLLECTION, filter='', limit=25,
            output_fields=[*store_module.FIELDS, 'embedding'], consistency_level='Strong', timeout=3)
        expected = {c['chunk_id']: {k: c[k] for k in ('chunk_id', 'doc_id', 'corpus_version', 'text_sha256', 'content_sha256')}
                    | {'model_revision': REVISION, 'provenance_sha256': store_module.provenance_sha(c)} for c in search.chunks}
        if len(actual) != 24 or {r['chunk_id'] for r in actual} != set(expected):raise ValueError('IDENTITY')
        for row in actual:
            v = row.get('embedding', [])
            if (any(row.get(k) != expected[row['chunk_id']][k] for k in store_module.FIELDS)
                    or len(v) != 384 or any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
                    or abs(sum(x*x for x in v) - 1) > 1e-4):raise ValueError('IDENTITY')
        verified_at = time.monotonic()
        stage = 'encoding'
        if not simulated:
            from importlib.metadata import version
            if version('torch')!='2.5.1+cpu' or version('transformers')!='4.44.2':
                raise RuntimeError('DEPENDENCY_VERSION')
        encoder = encoder_factory(payload['model_dir'], batch_size=1, threads=1)
        vectors, stats = encoder.encode([payload['question']], 'query')
        encoded_at = time.monotonic()
        if len(vectors) != 1 or len(vectors[0]) != 384:raise ValueError('ENCODING')
        # Réemploi du lecteur de Hit PyMilvus corrigé en J04, sans validate/load/ingest.
        stage = 'search'
        rows = store.search(vectors[0])
        hits = []
        for ident, score, entity in rows:
            if ident not in expected or any(entity.get(k) != expected[ident][k] for k in store_module.FIELDS):
                raise ValueError('IDENTITY')
            if not math.isfinite(score) or not -1.001 <= score <= 1.001:raise ValueError('IDENTITY')
            hits.append({'chunk_id': ident, 'score': score})
        if len(hits) > 24 or len({h['chunk_id'] for h in hits}) != len(hits):raise ValueError('IDENTITY')
        return {'status': 'ok', 'kind': 'TEST_DOUBLE_E5_MILVUS_READ_ONLY' if simulated else 'REAL_E5_MILVUS_READ_ONLY', 'collection': COLLECTION,
            'model_revision': REVISION, 'dimension': 384, 'metadata_verified': True,
            'vector_norms_verified': True, 'embeddings_recomputed': False,
            'hits': sorted(hits, key=lambda h: (-h['score'], h['chunk_id'])),
            'metadata_ms': round((verified_at-started)*1000, 3),
            'encoding_and_load_ms': round((encoded_at-verified_at)*1000, 3),
            'search_ms': round((time.monotonic()-encoded_at)*1000, 3)}
    except (KeyError, ValueError):
        return {'status': 'unavailable', 'code': 'E5_MODEL_OR_ENCODING_UNAVAILABLE' if stage=='encoding' else 'MILVUS_IDENTITY_MISMATCH'}
    except Exception:
        return {'status': 'unavailable', 'code': 'E5_MODEL_OR_ENCODING_UNAVAILABLE' if stage=='encoding' else 'MILVUS_NOT_AVAILABLE'}
    finally:
        if client is not None:
            try:client.close()
            except Exception:pass


def main():
    # stdout/stderr sont des fichiers temporaires bornés ; aucune sortie brute exposée.
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (4*1024**3, 4*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (18, 20))
    resource.setrlimit(resource.RLIMIT_FSIZE, (262144, 262144))
    payload = json.loads(sys.stdin.buffer.read(16385))
    if (set(payload) != {'uri', 'model_dir', 'question'} or not isinstance(payload['question'], str)
            or not 1 <= len(payload['question']) <= 600):
        result = {'status': 'unavailable', 'code': 'DENSE_RESOURCE_LIMIT'}
    else:result = perform(payload)
    print(json.dumps(result, allow_nan=False))


if __name__ == '__main__':main()
