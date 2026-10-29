"""API de récupération uniquement ; aucune réponse LLM inventée."""
from app.workflow_dispatch import dispatch

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from app.game import GameError
from app.advisor import RetrieveRequest, RetrievalResponse, AdvisorCapabilities


class AdvisorRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            if request.method=='POST':
                parts=[];size=0
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>16384:return JSONResponse(status_code=413,content={'detail':{'code':'ADVISOR_BODY_TOO_LARGE'}})
                    parts.append(chunk)
                request._body=b''.join(parts)
            try:return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422,content={'detail':{'code':'INVALID_ADVISOR_REQUEST'}})
            except GameError as error:
                return JSONResponse(status_code=error.status,content={'detail':{'code':error.code}})
        return handler


router = APIRouter(prefix='/api/v1/advisor', tags=['advisor'], route_class=AdvisorRoute)


@router.get('/capabilities',response_model=AdvisorCapabilities)
def capabilities(request: Request):
    return request.app.state.advisor.capabilities()


@router.post('/retrieve', response_model=RetrievalResponse)
def retrieve(body: RetrieveRequest, request: Request):
    return dispatch(request, 'retrieve_v1', body=body)
