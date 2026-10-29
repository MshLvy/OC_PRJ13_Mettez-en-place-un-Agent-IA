"""Identification factuelle locale : dernière position nommée d'un historique légal.

Aucune API ni moteur, aucune inférence de nom depuis la prose ou une FEN seule.
"""
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

import chess
from pydantic import BaseModel, ConfigDict, Field

from app.game import rebuild, snapshot

DATA = Path(__file__).with_name('data') / 'openings'
MAX_INDEX_BYTES = 4 * 1024 * 1024
CANDIDATE_LIMIT = 8
Status = Literal['identified', 'family_only', 'unknown', 'ambiguous', 'catalog_unavailable']


class Reference(BaseModel):
    model_config = ConfigDict(frozen=True)
    source: Literal['https://github.com/lichess-org/chess-openings']
    revision: str = Field(pattern=r'^[a-f0-9]{40}$')
    license: Literal['CC0-1.0']
    rows: int = Field(ge=1, le=10000)
    positions: int = Field(ge=1, le=10000)
    ambiguous_positions: int = Field(ge=0, le=10000)
    index_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    scope: Literal['all_rows_a_to_e_at_pinned_revision']


class Candidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    eco: str = Field(pattern=r'^[A-E][0-9]{2}$')
    full_name: str = Field(min_length=1, max_length=256)
    family: str = Field(min_length=1, max_length=256)
    variation: str | None = Field(default=None, max_length=256)
    source_file: str = Field(pattern=r'^[a-e]\.tsv$')
    source_line: int = Field(ge=2, le=10000)


class OpeningContext(BaseModel):
    """Données seulement pour un futur consommateur ; aucun RAG appelé ici."""
    fen: str
    history: list[str]
    family: str | None
    eco: str | None
    variation: str | None
    source: Literal['lichess_chess_openings_local'] = 'lichess_chess_openings_local'
    reference_revision: str | None
    certainty: Status
    is_current_match: bool
    last_matched_ply: int | None


class OpeningResponse(BaseModel):
    status: Status
    family: str | None = None
    variation: str | None = None
    full_name: str | None = None
    eco: str | None = None
    display_family: str | None = None
    language: Literal['fr', 'en', 'mixed'] | None = None
    last_matched_ply: int | None = Field(default=None, ge=1, le=256)
    matched_position_fen: str | None = None
    position_fen: str
    revision: int = Field(ge=0, le=256)
    snapshot: str
    is_current_match: bool = False
    off_line_since_ply: int | None = None
    possible_candidates: list[Candidate] = Field(default_factory=list, max_length=CANDIDATE_LIMIT)
    candidate_count: int = 0
    candidates_truncated: bool = False
    reference_revision: str | None = None
    reference: Reference | None = None
    context: OpeningContext


@dataclass(frozen=True)
class Catalog:
    positions: Mapping[str, tuple[Candidate, ...]]
    translations: Mapping[str, str]
    reference: Reference


def position_key(board):
    # La source définit EPD = placement/trait/roques/EP légal ; sans compteurs.
    return board.epd(en_passant='legal')


def canonical_candidates(values):
    # Même désignation : première ligne (fichier, numéro), indépendante de l'ordre d'entrée.
    unique = {}
    for c in sorted(values, key=lambda c: (c.source_file, c.source_line)):
        unique.setdefault((c.eco, c.full_name), c)
    return tuple(sorted(unique.values(), key=lambda c: (c.eco, c.full_name)))


def _read(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('CATALOG_SIZE_LIMIT')
    return raw


def read_catalog(root=DATA):
    """Lecture bornée de fichiers livrés avec l'application, sans récupération."""
    manifest = json.loads(_read(root / 'manifest.json', 16384))
    if manifest['schema'] != 1 or manifest['index']['file'] != 'catalog.json':
        raise ValueError('CATALOG_SCHEMA')
    expected = {'translations.fr.json', 'upstream/README.md', 'upstream/COPYING.txt'} | {'upstream/' + n + '.tsv' for n in 'abcde'}
    if set(manifest['files']) != expected:
        raise ValueError('CATALOG_FILES')
    for name in sorted(expected):
        raw = _read(root / name, 2 * 1024 * 1024)
        signature = manifest['files'][name]
        if len(raw) != signature['bytes'] or hashlib.sha256(raw).hexdigest() != signature['sha256']:
            raise ValueError('CATALOG_SOURCE_HASH')
    raw = _read(root / 'catalog.json', MAX_INDEX_BYTES)
    if len(raw) != manifest['index']['bytes'] or hashlib.sha256(raw).hexdigest() != manifest['index']['sha256']:
        raise ValueError('CATALOG_INDEX_HASH')
    data = json.loads(raw)
    if data['schema'] != 1 or data['revision'] != manifest['revision'] or len(data['entries']) != manifest['rows']:
        raise ValueError('CATALOG_INDEX_METADATA')
    reference = Reference(source=manifest['source'], revision=manifest['revision'], license=manifest['license'],
        rows=manifest['rows'], positions=manifest['positions'], ambiguous_positions=manifest['ambiguous_positions'],
        index_sha256=manifest['index']['sha256'], scope=manifest['scope'])
    grouped = {}
    for row in data['entries']:
        family, separator, variation = row['name'].partition(':')
        candidate = Candidate(eco=row['eco'], full_name=row['name'], family=family.strip(),
            variation=variation.strip() if separator else None, source_file=row['source_file'], source_line=row['source_line'])
        grouped.setdefault(row['key'], []).append(candidate)
    positions = {key: canonical_candidates(values) for key, values in grouped.items()}
    if len(positions) != reference.positions or sum(len(v) > 1 for v in positions.values()) != reference.ambiguous_positions:
        raise ValueError('CATALOG_COUNTS')
    translations = json.loads(_read(root / 'translations.fr.json', 16384))
    if translations['schema'] != 1 or not all(isinstance(k, str) and isinstance(v, str) for k, v in translations['families'].items()):
        raise ValueError('CATALOG_TRANSLATIONS')
    return Catalog(MappingProxyType(positions), MappingProxyType(translations['families']), reference)


@lru_cache(maxsize=1)
def load_catalog():
    # Le paquet est immuable pendant un lancement ; indisponibilité reste explicite.
    try:
        return read_catalog()
    except (OSError, ValueError, KeyError, TypeError):
        return None


class OpeningIdentifier:
    def __init__(self, loader=load_catalog):
        self.loader = loader

    def identify(self, history):
        # Rejouer depuis le début est borné à256 demi-coups, autorité identique au jeu.
        board, _ = rebuild(history)
        current_fen = board.fen(en_passant='fen')
        try:
            catalog = self.loader()
        except (OSError, ValueError, KeyError, TypeError):
            catalog = None
        last, matched_fen, candidates = None, None, ()
        if catalog is not None:
            cursor = chess.Board()
            for ply, move in enumerate(history, 1):
                cursor.push_uci(move)
                found = catalog.positions.get(position_key(cursor))
                if found:
                    last, matched_fen, candidates = ply, cursor.fen(en_passant='fen'), canonical_candidates(found)
        family = variation = name = eco = display = language = None
        status = 'catalog_unavailable' if catalog is None else 'unknown'
        if candidates:
            if len(candidates) == 1:
                candidate = candidates[0]
                family, variation, name, eco = candidate.family, candidate.variation, candidate.full_name, candidate.eco
                status = 'identified' if variation else 'family_only'
            else:
                status = 'ambiguous'
                families, codes = {c.family for c in candidates}, {c.eco for c in candidates}
                family = next(iter(families)) if len(families) == 1 else None
                eco = next(iter(codes)) if len(codes) == 1 else None
            if family:
                display = catalog.translations.get(family, family)
                language = ('mixed' if variation else 'fr') if family in catalog.translations else 'en'
        current_match = last == len(history) if last is not None else False
        reference = catalog.reference if catalog else None
        revision = reference.revision if reference else None
        context = OpeningContext(fen=current_fen, history=list(history), family=family, eco=eco,
            variation=variation, reference_revision=revision, certainty=status,
            is_current_match=current_match, last_matched_ply=last)
        return OpeningResponse(status=status, family=family, variation=variation, full_name=name, eco=eco,
            display_family=display, language=language, last_matched_ply=last, matched_position_fen=matched_fen,
            position_fen=current_fen, revision=len(history), snapshot=snapshot(history), is_current_match=current_match,
            off_line_since_ply=last + 1 if last is not None and not current_match else None,
            possible_candidates=list(candidates[:CANDIDATE_LIMIT]), candidate_count=len(candidates),
            candidates_truncated=len(candidates) > CANDIDATE_LIMIT,
            reference_revision=revision, reference=reference, context=context)
