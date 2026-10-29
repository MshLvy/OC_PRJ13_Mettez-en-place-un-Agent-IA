"""Route imposée : catch-all limité au préfixe /api/v1/moves/."""
from app.workflow_dispatch import dispatch


from typing import Annotated, Literal
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.explorer import MOVE_LIMIT, ExplorerError, SourceMode
from app.positions import FenValidationError

router = APIRouter(prefix="/api/v1/moves", tags=["moves"])


class StatisticsResponse(BaseModel):
    white: int
    draws: int
    black: int
    games: int


class MoveResponse(BaseModel):
    uci: str
    san: str
    statistics: StatisticsResponse | None


class MovesResponse(BaseModel):
    status: Literal["ok", "empty", "terminal"]
    fen_normalized: str
    source: Literal["lichess_opening_explorer"]
    source_mode: SourceMode
    base: Literal["masters"]
    position_statistics: StatisticsResponse | None
    moves: Annotated[list[MoveResponse], Field(max_length=MOVE_LIMIT)]
    moves_truncated: bool


@router.get("/{fen:path}", response_model=MovesResponse)
def get_moves(fen: str, request: Request) -> MovesResponse:
    # ASGI/TestClient peut déjà avoir décodé scope.path deux fois. La cible
    # brute permet de contrôler un seul décodage, sans appeler unquote(fen).
    raw_path = request.scope.get("raw_path")
    if raw_path is not None:
        prefix = b"/api/v1/moves/"
        try:
            if not raw_path.startswith(prefix):
                raise ValueError("Unexpected raw path prefix")
            fen = unquote_to_bytes(raw_path[len(prefix):]).decode("ascii")
        except (UnicodeError, ValueError):
            raise HTTPException(422, detail={"code": "INVALID_FEN_FORMAT", "issues": []}) from None
    try:
        result = dispatch(request, 'moves', fen=fen)
    except FenValidationError as exc:
        raise HTTPException(422, detail={"code": exc.code, "issues": list(exc.issues)}) from None
    except ExplorerError as exc:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        raise HTTPException(exc.http_status,
                            detail={"code": exc.code, "retry_after_seconds": exc.retry_after},
                            headers=headers) from None
    return MovesResponse.model_validate(result, from_attributes=True)
