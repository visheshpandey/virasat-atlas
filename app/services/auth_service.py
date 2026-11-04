from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
from app.schemas.user import UserOut
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def register_user(data: RegisterRequest, db: AsyncSession) -> UserOut:
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        phone=data.phone,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"user_registered email={data.email}")
    return UserOut.model_validate(user)


async def login_user(data: LoginRequest, db: AsyncSession) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(str(user.id), user.email)
    refresh_token = create_refresh_token(str(user.id))
    logger.info(f"user_login email={data.email}")
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
