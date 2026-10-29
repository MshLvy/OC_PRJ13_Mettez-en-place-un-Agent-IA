"""Évaluation moteur ; GET imposé, même convention de transport FEN que moves."""
from app.workflow_dispatch import dispatch


from typing import Literal
from urllib.parse import unquote_to_bytes

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.position_routes import PositionResponse
from app.positions import FenValidationError
from app.stockfish import EvaluationLimits, EvaluationScore, StockfishError

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


class EvaluationResponse(BaseModel):
    status: Literal["ok", "terminal"]
    fen_normalized: str
    source: Literal["stockfish"]
    source_mode: Literal["local_engine"]
    engine_version: str | None
    depth: int | None
    limits: EvaluationLimits
    score: EvaluationScore | None
    best_move_uci: str | None
    best_move_san: str | None
    position: PositionResponse


@router.get("/{fen:path}", response_model=EvaluationResponse)
def evaluate_position(fen: str, request: Request):
    raw_path = request.scope.get("raw_path")
    if raw_path is not None:
        prefix = b"/api/v1/evaluate/"
        try:
            if not raw_path.startswith(prefix):
                raise ValueError
            fen = unquote_to_bytes(raw_path[len(prefix):]).decode("ascii")
        except (ValueError, UnicodeError):
            raise HTTPException(422, detail={"code": "INVALID_FEN_FORMAT", "issues": []}) from None
    try:
        result = dispatch(request, 'evaluate', fen=fen)
    except FenValidationError as error:
        raise HTTPException(422, detail={"code": error.code, "issues": list(error.issues)}) from None
    except StockfishError as error:
        raise HTTPException(error.http_status, detail={"code": error.code}) from None
    return EvaluationResponse.model_validate(result, from_attributes=True)
