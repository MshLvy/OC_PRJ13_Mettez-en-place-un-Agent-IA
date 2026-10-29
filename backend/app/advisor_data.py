"""Legacy compatibility: experimental V1 archives are not release assets."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def policy():raise ValueError('LEGACY_CORPUS_NOT_DISTRIBUTED')
def load_search():raise ValueError('LEGACY_CORPUS_NOT_DISTRIBUTED')
def legacy_modules():raise ValueError('LEGACY_CORPUS_NOT_DISTRIBUTED')
