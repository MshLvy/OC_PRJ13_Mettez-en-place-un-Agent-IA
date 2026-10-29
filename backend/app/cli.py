"""Lanceur local : dotenv explicite, aucune lecture de .env lors d'un import."""

import argparse
from io import StringIO
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn

MAX_ENV_FILE_BYTES = 65536


class EnvFileError(ValueError):
    """Diagnostic sans contenu ni valeur de configuration."""


def load_env_file(path: str) -> None:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_ENV_FILE_BYTES + 1)
    except (OSError, ValueError):
        raise EnvFileError("ENV_FILE_UNREADABLE") from None
    if len(raw) > MAX_ENV_FILE_BYTES:
        raise EnvFileError("ENV_FILE_TOO_LARGE")
    try:
        content = raw.decode("utf-8")
    except UnicodeError:
        raise EnvFileError("ENV_FILE_INVALID_ENCODING") from None
    # Pas de recherche implicite ni d'expansion ${...}, notamment des références
    # de secrets injectés. Les variables de processus déjà définies gagnent.
    load_dotenv(stream=StringIO(content), override=False, interpolate=False)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backend local du Projet 13")
    parser.add_argument("--env-file", help="Fichier dotenv à charger explicitement")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, help="Prioritaire sur BACKEND_PORT")
    args = parser.parse_args(argv)
    if args.env_file is not None:
        try:
            load_env_file(args.env_file)
        except EnvFileError as error:
            parser.exit(2, str(error) + "\n")
    try:
        port = args.port if args.port is not None else int(os.getenv("BACKEND_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        parser.exit(2, "BACKEND_PORT must be an integer between 1 and 65535\n")
    # L'application est importée par Uvicorn seulement après chargement demandé.
    uvicorn.run("app.main:app", host=args.host, port=port)
