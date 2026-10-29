"""Routes stateless, erreurs sans réémettre le corps utilisateur."""
from app.workflow_dispatch import dispatch

from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from app.videos_routes import VideoRoute
from app.game import HistoryRequest,TurnRequest,GameState,TurnResponse,GameError,rebuild,state_from

class GameRoute(VideoRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            try:
                response=await original(request)
                if response.status_code==422:
                    return JSONResponse(status_code=422,content={'detail':{'code':'INVALID_GAME_REQUEST'}})
                return response
            except GameError as error:
                return JSONResponse(status_code=error.status,content={'detail':{'code':error.code}})
        return handler

router=APIRouter(prefix='/api/v1/game',tags=['game'],route_class=GameRoute)
@router.post('/state',response_model=GameState)
def game_state(body:HistoryRequest,request:Request):
    return dispatch(request, 'game_state', body=body)
@router.post('/turn',response_model=TurnResponse)
def game_turn(body:TurnRequest,request:Request):
    return dispatch(request, 'game_turn', body=body)
