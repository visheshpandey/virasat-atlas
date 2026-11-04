"""Current user profile."""
from fastapi import APIRouter, Depends

from app.models.user import User
from app.routes.deps import get_current_user
from app.schemas.user import UserOut

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
