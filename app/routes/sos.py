from fastapi import APIRouter, Depends

from app.models.user import User
from app.schemas.sos import SOSRequest, SOSResponse
from app.routes.deps import get_current_user
from app.services.sos_service import trigger_sos

router = APIRouter(prefix="/sos", tags=["sos"])


@router.post("/trigger", response_model=SOSResponse)
async def sos_trigger(
    data: SOSRequest,
    current_user: User = Depends(get_current_user),
):
    return await trigger_sos(data, current_user)
