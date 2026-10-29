"""Contrat vidéo isolé ; erreurs de validation sans réémettre le contenu fourni."""
from app.workflow_dispatch import dispatch

from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from app.videos import VideoRequest, VideoResult
from app.video_exploration import ExploreRequest, ExplorationResponse, VideoExplorationBusy


class VideoRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(status_code=422, content={'detail': {'code': 'INVALID_VIDEO_REQUEST'}})
        return handler


router = APIRouter(prefix='/api/v1/videos', tags=['videos'], route_class=VideoRoute)


@router.post('/search', response_model=VideoResult)
def search_videos(payload: VideoRequest, request: Request) -> VideoResult:
    return dispatch(request, 'videos_search', body=payload)


@router.post('/explore', response_model=ExplorationResponse)
def explore_videos(payload: ExploreRequest, request: Request) -> ExplorationResponse:
    try:
        return dispatch(request, 'videos_explore', body=payload)
    except VideoExplorationBusy:
        return JSONResponse(status_code=503, content={'detail': {'code': 'VIDEO_EXPLORATION_BUSY'}})

@router.get('/{opening}', response_model=VideoResult)
def videos_by_opening(opening: str, request: Request,
                      confirm_live: bool = Query(default=False)):
    try:
        body = VideoRequest(opening=opening)
    except ValueError:
        raise HTTPException(422, detail={'code':'INVALID_VIDEO_REQUEST'}) from None
    # A GET can be prefetched: a live server therefore requires explicit query
    # confirmation in addition to the existing server opt-in and shared quotas.
    if request.app.state.videos.mode == 'live' and not confirm_live:
        raise HTTPException(403, detail={'code':'YOUTUBE_LIVE_CONFIRMATION_REQUIRED'})
    return dispatch(request, 'videos_search', body=body)
