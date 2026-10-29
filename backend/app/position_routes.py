"""Contrat HTTP du diagnostic FEN ; la logique d'échecs reste dans positions."""
from app.workflow_dispatch import dispatch


from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.positions import (
    MAX_FEN_LENGTH,
    MAX_RETURNED_MOVES,
    FenValidationError,
    Termination,
    diagnose_fen,
)

router = APIRouter(prefix="/api/v1/positions", tags=["positions"])


class PositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fen: Annotated[str, Field(strict=True, min_length=1, max_length=MAX_FEN_LENGTH)]


class PositionResponse(BaseModel):
    valid: Literal[True]
    fen_normalized: str
    side_to_move: Literal["white", "black"]
    legal_moves_count: int
    legal_moves_uci: Annotated[list[str], Field(max_length=MAX_RETURNED_MOVES)]
    legal_moves_truncated: bool
    is_check: bool
    is_checkmate: bool
    is_stalemate: bool
    is_insufficient_material: bool
    is_terminal: bool
    termination: Termination | None
    history_available: Literal[False]
    repetition_status: Literal["unknown_without_history"]


@router.post("/validate", response_model=PositionResponse)
async def validate_position(body: PositionRequest, request: Request) -> PositionResponse:
    """Valide une position orthodoxe, puis décrit ses possibilités légales."""
    try:
        diagnostic = dispatch(request, "position_validate", body=body)
    except FenValidationError as exc:
        message = (
            "Une FEN standard complète à six champs est requise."
            if exc.code == "INVALID_FEN_FORMAT"
            else "Position incohérente selon python-chess."
        )
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": message, "issues": list(exc.issues)},
        ) from None
    return PositionResponse.model_validate(diagnostic, from_attributes=True)
