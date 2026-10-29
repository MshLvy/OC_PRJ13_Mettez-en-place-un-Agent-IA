"""Conversion locale déterministe des cinq TSV officiels, sans acquisition réseau."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re

import chess
import chess.pgn

REVISION = 'a6189a30dc273ccb21fc2536a9a2fefd5592a67a'
SOURCE = 'https://github.com/lichess-org/chess-openings'
DEFAULT = Path(__file__).resolve().parents[2] / 'backend/app/data/openings'


def encode(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def build(root=DEFAULT):
    entries = []
    files = {}
    counts = {}
    for name in ('a.tsv', 'b.tsv', 'c.tsv', 'd.tsv', 'e.tsv', 'README.md', 'COPYING.txt'):
        path = root / 'upstream' / name
        raw = path.read_bytes()
        files['upstream/' + name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
            'url': SOURCE + '/blob/' + REVISION + '/' + name}
        if not name.endswith('.tsv'):
            continue
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8')), delimiter='\t')
        if reader.fieldnames != ['eco', 'name', 'pgn']:
            raise ValueError('CATALOG_COLUMNS')
        count = 0
        for line, row in enumerate(reader, 2):
            if not re.fullmatch('[A-E][0-9]{2}', row['eco']) or not row['name'] or len(row['name']) > 256:
                raise ValueError('CATALOG_DESIGNATION')
            stream = io.StringIO(row['pgn'])
            game = chess.pgn.read_game(stream)
            if game is None or game.errors or game.board().fen() != chess.STARTING_FEN:
                raise ValueError('CATALOG_PGN')
            board = game.board()
            uci = []
            for move in game.mainline_moves():
                if move not in board.legal_moves:
                    raise ValueError('CATALOG_ILLEGAL_MOVE')
                uci.append(move.uci())
                board.push(move)
            if not uci or len(uci) > 256 or chess.pgn.read_game(stream) is not None:
                raise ValueError('CATALOG_LENGTH')
            entries.append({'eco': row['eco'], 'name': row['name'], 'pgn': row['pgn'], 'uci': uci,
                'key': board.epd(en_passant='legal'), 'source_file': name, 'source_line': line})
            count += 1
        counts[name] = count
    names = {e['name'].partition(':')[0].strip() for e in entries}
    translations = json.loads((root / 'translations.fr.json').read_text())
    if not set(translations['families']) <= names:
        raise ValueError('TRANSLATION_FAMILY_NOT_IN_REFERENCE')
    raw = (root / 'translations.fr.json').read_bytes()
    files['translations.fr.json'] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    index = encode({'schema': 1, 'revision': REVISION, 'entries': entries})
    grouped = defaultdict(set)
    for e in entries:
        grouped[e['key']].add((e['eco'], e['name']))
    manifest = {'schema': 1, 'revision': REVISION, 'source': SOURCE, 'license': 'CC0-1.0',
        'collected_on': '2026-10-26', 'scope': 'all_rows_a_to_e_at_pinned_revision', 'files': files,
        'index': {'file': 'catalog.json', 'sha256': hashlib.sha256(index).hexdigest(), 'bytes': len(index)},
        'rows': len(entries), 'rows_by_file': counts, 'positions': len(grouped),
        'ambiguous_positions': sum(len(v) > 1 for v in grouped.values()),
        'max_distinct_designations_at_position': max(map(len, grouped.values())),
        'python_chess_library': chess.__version__,
        'conversion': 'PGN legal mainline from standard start -> UCI + board.epd(en_passant=legal), no counters',
        'generator': 'tools/openings/build_catalog.py'}
    return index, (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    index, manifest = build()
    if args.check:
        assert (DEFAULT / 'catalog.json').read_bytes() == index, 'CATALOG_NOT_REPRODUCIBLE'
        assert (DEFAULT / 'manifest.json').read_bytes() == manifest, 'MANIFEST_NOT_REPRODUCIBLE'
        print('PASS: catalog and manifest byte-identical, all PGN mainlines legal')
    else:
        (DEFAULT / 'catalog.json').write_bytes(index)
        (DEFAULT / 'manifest.json').write_bytes(manifest)
        print(manifest.decode())


if __name__ == '__main__':
    main()
