"""Données SYNTHÉTIQUES : ni capture Lichess, ni statistiques historiques réelles."""

import chess
import httpx2 as httpx

SYNTHETIC_MASTERS_INITIAL = {
    "white": 9, "draws": 6, "black": 5,
    "moves": [
        {"uci": "e2e4", "san": "e4", "white": 6, "draws": 2, "black": 2},
        {"uci": "d2d4", "san": "d4", "white": 3, "draws": 4, "black": 3},
    ],
}


def synthetic_transport(request: httpx.Request) -> httpx.Response:
    """Fixture déterministe pour démonstration HTTP, aucun socket réseau."""
    payload = (SYNTHETIC_MASTERS_INITIAL
               if request.url.params.get("fen") == chess.STARTING_FEN
               else {"white": 0, "draws": 0, "black": 0, "moves": []})
    return httpx.Response(200, json=payload)
