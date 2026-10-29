from app.workflow_dispatch import dispatch
from fastapi import APIRouter,Request
from app.advisor_routes import AdvisorRoute
from app.conversation import ConversationRequest,ConversationResponse
router=APIRouter(prefix='/api/v1/advisor',tags=['conversation'],route_class=AdvisorRoute)
@router.post('/conversation',response_model=ConversationResponse)
def conversation(body:ConversationRequest,request:Request):
    result=dispatch(request, 'conversation', body=body)
    return result
