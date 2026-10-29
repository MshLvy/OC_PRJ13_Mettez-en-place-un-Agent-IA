"""Client live opt-in : environnement prioritaire, fichier alternatif, sans I/O réseau au démarrage."""

import os
from pathlib import Path

import httpx2 as httpx

from app.explorer import ENDPOINT, TIMEOUT_SECONDS

MAX_TOKEN_BYTES = 4096


class SecretConfigurationError(ValueError):
    """Diagnostic stable ; ne contient jamais le chemin ni le contenu du secret."""


def _validate_token(raw: bytes) -> str:
    if len(raw) > MAX_TOKEN_BYTES:
        raise SecretConfigurationError("LICHESS_SECRET_INVALID")
    try:
        token = raw.decode("ascii").strip()
    except UnicodeError:
        raise SecretConfigurationError("LICHESS_SECRET_INVALID") from None
    # Interdit les contrôles/injections de headers, sans supposer le format du
    # jeton : un environnement géré peut fournir une référence de secret que
    # son proxy substitue lors du transport. Ne jamais en inspecter le contenu.
    if not token or any(ord(char) < 32 or ord(char) >= 127 for char in token):
        raise SecretConfigurationError("LICHESS_SECRET_INVALID")
    return token


def read_token(token_file: str) -> str:
    """Voie fichier historique, explicitement sélectionnée par son appelant."""
    try:
        with Path(token_file).open("rb") as stream:
            raw = stream.read(MAX_TOKEN_BYTES + 1)
    except (OSError, ValueError):
        raise SecretConfigurationError("LICHESS_SECRET_UNREADABLE") from None
    return _validate_token(raw)


class LichessBearer(httpx.Auth):
    """Ne place pas le secret dans les headers par défaut ni dans un repr."""

    def __init__(self, token: str):
        self._token = token

    def auth_flow(self, request):
        url = request.url
        if (url.scheme != "https" or url.host != "explorer.lichess.org"
                or url.port not in (None, 443) or url.path != "/masters"
                or url.userinfo):
            raise SecretConfigurationError("LICHESS_AUTH_TARGET_REJECTED")
        request.headers["Authorization"] = "Bearer " + self._token
        yield request


def _client(token: str, *, transport=None) -> httpx.Client:
    # Le transport injectable conserve les mêmes garanties d'auth pour les mocks.
    # HTTPX utilise TLS vérifié, les proxies/CA de l'environnement et zéro retry
    # par défaut. Aucun request hook ni journal HTTP contenant les headers.
    return httpx.Client(auth=LichessBearer(token), transport=transport,
                        timeout=TIMEOUT_SECONDS, follow_redirects=False,
                        base_url=ENDPOINT)


def live_client(token_file: str, *, transport=None) -> httpx.Client:
    """Compatibilité des appelants qui choisissent explicitement le fichier."""
    return _client(read_token(token_file), transport=transport)


def configured_live_client(token_file: str, *, transport=None) -> httpx.Client:
    """Env non vide > fichier ; une valeur env invalide ne déclenche aucun repli."""
    token = os.getenv("LICHESS_API_TOKEN")
    if token is not None and token.strip():
        try:
            raw = token.encode("ascii")
        except UnicodeError:
            raise SecretConfigurationError("LICHESS_SECRET_INVALID") from None
        return _client(_validate_token(raw), transport=transport)
    return live_client(token_file, transport=transport)
