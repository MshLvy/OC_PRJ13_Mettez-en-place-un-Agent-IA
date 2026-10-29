"""Brief endpoint: dense passages or explicit unavailability, never lexical success."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.advisor_routes import AdvisorRoute
from app.vector_search import VectorRequest, VectorResponse
from app.workflow_dispatch import dispatch

router = APIRouter(tags=['vector-search'], route_class=AdvisorRoute)

@router.post('/vector-search', response_model=VectorResponse)
def vector_search(body: VectorRequest, request: Request):
    result = dispatch(request, 'vector_search', body=body)
    if result.status in ('unavailable', 'invalid'):
        return JSONResponse(status_code=503 if result.status == 'unavailable' else 422,
                            content=result.model_dump())
    return result
