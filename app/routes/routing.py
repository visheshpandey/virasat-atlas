from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.route import RouteRequest, RouteResponse
from app.routes.deps import get_current_user
from app.services.routing_service import compute_safest_route, compute_shortest_route

router = APIRouter(prefix="/route", tags=["routing"])


@router.post("/safest", response_model=RouteResponse)
async def safest_route(
    data: RouteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await compute_safest_route(
        data.source_lat, data.source_lng,
        data.dest_lat, data.dest_lng,
        current_user.id, db,
    )


@router.post("/shortest", response_model=RouteResponse)
async def shortest_route(
    data: RouteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await compute_shortest_route(
        data.source_lat, data.source_lng,
        data.dest_lat, data.dest_lng,
        current_user.id, db,
    )
