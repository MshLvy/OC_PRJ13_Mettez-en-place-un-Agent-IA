"""Résolution pure : HTTP > défaut serveur, toujours sous le plafond serveur."""

from pydantic import BaseModel
from typing import Literal

from app.config import ExplorerMode, EXPLORER_LEVELS, Settings


class PreferenceError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class ExplorerPreference(BaseModel):
    ceiling: ExplorerMode
    default: ExplorerMode
    requested: ExplorerMode | None
    legacy_include: bool | None
    resolved: ExplorerMode
    origin: Literal["default", "http", "legacy"]


class EnginePreference(BaseModel):
    allowed: bool
    default: bool
    requested: bool | None
    resolved: bool
    origin: Literal["default", "http"]


class ResolvedPreferences(BaseModel):
    explorer: ExplorerPreference
    engine: EnginePreference


def resolve_preferences(settings: Settings, *, explorer_mode=None, include_explorer=None,
                        include_engine=None) -> ResolvedPreferences:
    # Défense également pour les appelants Python, au-delà du DTO HTTP strict.
    if ((explorer_mode is not None and (not isinstance(explorer_mode, str) or explorer_mode not in EXPLORER_LEVELS))
            or any(value is not None and type(value) is not bool for value in (include_explorer, include_engine))):
        raise PreferenceError("INVALID_ANALYSIS_PREFERENCES")
    if explorer_mode is not None:
        if include_explorer is not None and include_explorer != (explorer_mode != "disabled"):
            raise PreferenceError("CONFLICTING_EXPLORER_PREFERENCES")
        resolved, origin = explorer_mode, "http"
    elif include_explorer is not None:
        # Transition I04 : true choisit le défaut actif, sinon le plafond historique.
        resolved = (settings.explorer_default_mode if settings.explorer_default_mode != "disabled"
                    else settings.explorer_mode) if include_explorer else "disabled"
        origin = "legacy"
        if include_explorer and resolved == "disabled":
            raise PreferenceError("EXPLORER_MODE_NOT_ALLOWED")
    else:
        resolved, origin = settings.explorer_default_mode, "default"
    engine = settings.analysis_default_engine if include_engine is None else include_engine
    if EXPLORER_LEVELS[resolved] > EXPLORER_LEVELS[settings.explorer_mode]:
        raise PreferenceError("EXPLORER_MODE_NOT_ALLOWED")
    if engine and not settings.stockfish.enabled:
        raise PreferenceError("ENGINE_NOT_ALLOWED")
    return ResolvedPreferences(
        explorer=ExplorerPreference(ceiling=settings.explorer_mode, default=settings.explorer_default_mode,
            requested=explorer_mode, legacy_include=include_explorer, resolved=resolved, origin=origin),
        engine=EnginePreference(allowed=settings.stockfish.enabled, default=settings.analysis_default_engine,
            requested=include_engine, resolved=engine, origin="default" if include_engine is None else "http"))
