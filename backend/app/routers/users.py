"""User self-service endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models import User
from app.schemas.auth import UserOut

router = APIRouter()


@router.get("/me", summary="Current user profile", response_model=UserOut)
async def me(
    claims: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> UserOut:
    user_id = claims["sub"]
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        # The JWT referenced a user that has since been deleted. Don't
        # leak the matrix: same response as "no token".
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "User not found"},
        )
    return UserOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
