"""Configuration minimale, lue au démarrage de l'application."""

import os
import math
from dataclasses import dataclass, field
from typing import Literal

ExplorerMode = Literal["disabled", "synthetic_fixture", "live"]
EXPLORER_LEVELS = {"disabled": 0, "synthetic_fixture": 1, "live": 2}


@dataclass(frozen=True)
class StockfishSettings:
    enabled: bool = False
    path: str = "/usr/games/stockfish"
    time_seconds: float = 0.5

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("INVALID_STOCKFISH_ENABLED")
        if (not isinstance(self.path, str) or not self.path.startswith("/")
                or len(self.path) > 4096 or any(ord(c) < 32 for c in self.path)):
            raise ValueError("INVALID_STOCKFISH_PATH")
        if (type(self.time_seconds) not in (int, float) or not math.isfinite(self.time_seconds)
                or not 0.05 <= self.time_seconds <= 1.0):
            raise ValueError("INVALID_STOCKFISH_TIME_SECONDS")

    @classmethod
    def from_env(cls):
        enabled = os.getenv("STOCKFISH_ENABLED", "false").lower()
        if enabled not in ("true", "false"):
            raise ValueError("INVALID_STOCKFISH_ENABLED")
        try:
            seconds = float(os.getenv("STOCKFISH_TIME_SECONDS", "0.5"))
        except ValueError:
            raise ValueError("INVALID_STOCKFISH_TIME_SECONDS") from None
        return cls(enabled == "true", os.getenv("STOCKFISH_PATH", "/usr/games/stockfish"), seconds)


@dataclass(frozen=True)
class Settings:
    app_name: str
    explorer_mode: ExplorerMode = "disabled"
    lichess_token_file: str = "/run/secrets/lichess_token"
    stockfish: StockfishSettings = field(default_factory=StockfishSettings)

    explorer_default_mode: ExplorerMode = "disabled"
    analysis_default_engine: bool = False

    def __post_init__(self):
        if self.explorer_mode not in EXPLORER_LEVELS:
            raise ValueError("INVALID_EXPLORER_MODE")
        if self.explorer_default_mode not in EXPLORER_LEVELS:
            raise ValueError("INVALID_EXPLORER_DEFAULT_MODE")
        if EXPLORER_LEVELS[self.explorer_default_mode] > EXPLORER_LEVELS[self.explorer_mode]:
            raise ValueError("EXPLORER_DEFAULT_MODE_NOT_ALLOWED")
        if type(self.analysis_default_engine) is not bool:
            raise ValueError("INVALID_ANALYSIS_DEFAULT_ENGINE")
        if self.analysis_default_engine and not self.stockfish.enabled:
            raise ValueError("ANALYSIS_DEFAULT_ENGINE_NOT_ALLOWED")

    @classmethod
    def from_env(cls) -> "Settings":
        app_name = os.getenv("APP_NAME", "OC Projet 13").strip()
        if not app_name:
            raise ValueError("APP_NAME must not be empty")
        explorer_mode = os.getenv("EXPLORER_MODE", "disabled")
        if explorer_mode not in ("disabled", "synthetic_fixture", "live"):
            raise ValueError("EXPLORER_MODE must be disabled, synthetic_fixture or live")
        engine_default = os.getenv("ANALYSIS_DEFAULT_ENGINE", "false").lower()
        if engine_default not in ("true", "false"):
            raise ValueError("INVALID_ANALYSIS_DEFAULT_ENGINE")
        return cls(app_name=app_name, explorer_mode=explorer_mode,
                   explorer_default_mode=os.getenv("EXPLORER_DEFAULT_MODE", "disabled"),
                   analysis_default_engine=engine_default == "true",
                   lichess_token_file=os.getenv("LICHESS_API_TOKEN_FILE", "/run/secrets/lichess_token"),
                   stockfish=StockfishSettings.from_env())
