"""Local-only session CRUD. No dynamic Mongo URI or untrusted answer payload."""
from app.workflow_dispatch import dispatch

from fastapi import APIRouter,Request,Query,Path
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from app.game import GameError
from app.sessions import SessionDraft,SessionRecord,SessionFailure,ID
class SessionRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def handler(request):
            if request.method=='POST':
                parts=[];size=0
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>196608:return JSONResponse(status_code=413,content={'detail':{'code':'SESSION_BODY_TOO_LARGE'}})
                    parts.append(chunk)
                request._body=b''.join(parts)
            try:return await original(request)
            except (RequestValidationError,GameError):return JSONResponse(status_code=422,content={'detail':{'code':'INVALID_SESSION_REQUEST'}})
            except SessionFailure as error:return JSONResponse(status_code=error.status,content={'detail':{'code':error.code}})
        return handler
router=APIRouter(prefix='/api/v1/sessions',tags=['sessions'],route_class=SessionRoute)
@router.get('/status')
def status(request:Request):return {'status':request.app.state.session_store.status()}
@router.post('',response_model=SessionRecord,status_code=201)
def create(body:SessionDraft,request:Request):return dispatch(request, 'session_create', body=body)
@router.get('')
def listing(request:Request,limit:int=Query(default=10,ge=1,le=20),after:str|None=Query(default=None,pattern=ID)):
    return dispatch(request, 'session_list', after=after, limit=limit)
@router.get('/{ident}',response_model=SessionRecord)
def get(request:Request,ident:str=Path(pattern=ID)):
    return dispatch(request, 'session_get', ident=ident)
@router.delete('/{ident}')
def delete(request:Request,ident:str=Path(pattern=ID)):
    return dispatch(request, 'session_delete', ident=ident)

@router.post('/{ident}/resume',response_model=SessionRecord)
def prepare_resume(request:Request,ident:str=Path(pattern=ID)):
    # Read/validate only. Angular still applies the state explicitly via game/state.
    return dispatch(request, 'session_resume', ident=ident)
