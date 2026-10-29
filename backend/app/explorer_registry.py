"""Registre de services distincts : aucun changement global de mode par requête."""

from types import MappingProxyType

from app.explorer import ExplorerError, OpeningExplorer
from app.positions import diagnose_fen


class UnavailableLiveExplorer(OpeningExplorer):
    def __init__(self, code):
        super().__init__(None, "live")
        self.code = code if code in ("LICHESS_SECRET_INVALID", "LICHESS_SECRET_UNREADABLE") else "LICHESS_CONFIGURATION_UNAVAILABLE"

    def moves(self, fen):
        if diagnose_fen(fen).is_terminal:
            return super().moves(fen)
        raise ExplorerError(self.code, 503)


def explorer_registry(disabled, synthetic=None, live=None):
    return MappingProxyType({mode: adapter for mode, adapter in
        (("disabled", disabled), ("synthetic_fixture", synthetic), ("live", live)) if adapter is not None})
