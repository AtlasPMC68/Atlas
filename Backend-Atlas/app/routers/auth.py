from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from ..db import get_db
from ..utils.auth import get_user_from_token
from ..utils.user import get_user_by_id, create_user
from ..keycloak import get_keycloak_public_key

router = APIRouter()

@router.get("/me")
def me(user: dict = Depends(get_user_from_token), db: Session = Depends(get_db)):
    user_id = UUID(user["sub"])
    db_user = get_user_by_id(db, user_id)
    
    if not db_user:
        db_user = create_user(
            db=db,
            user_id=user_id,
            email=user.get("email"),
            username=user.get("preferred_username")
        )
    
    return {
        "id": str(db_user.id),
        "username": db_user.username,
        "email": db_user.email,
        "created_at": db_user.created_at,
    }

@router.get("/public-key")
def get_public_key():
    return {"public_key": get_keycloak_public_key()}