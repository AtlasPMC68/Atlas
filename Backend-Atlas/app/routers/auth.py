from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import get_db
from ..utils.auth import get_current_user
from ..utils.user import get_or_create_user
from ..keycloak import get_keycloak_public_key

router = APIRouter()

@router.get("/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    db_user = get_or_create_user(db, user)
    return {
        "id": str(db_user.id),
        "username": db_user.username,
        "email": db_user.email,
        "created_at": db_user.created_at,
    }

@router.get("/public-key")
def get_public_key():
    return {"public_key": get_keycloak_public_key()}
