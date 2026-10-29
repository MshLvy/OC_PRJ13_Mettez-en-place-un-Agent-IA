"""Route additive locale, indépendante des autorisations fournisseurs de démo."""
from app.workflow_dispatch import dispatch

from fastapi import APIRouter, Request
from app.game import HistoryRequest
from app.game_routes import GameRoute
from app.openings import OpeningResponse

router = APIRouter(prefix='/api/v1/openings', tags=['openings'], route_class=GameRoute)


@router.post('/identify', response_model=OpeningResponse)
def identify(body: HistoryRequest, request: Request):
    return dispatch(request, 'opening_identify', body=body)
