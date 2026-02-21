from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from ..db import get_db
from ..utils.user import get_user_by_id
from ..utils.auth import get_user_from_token

router = APIRouter()

@router.get("/profile")
def profile(user: dict = Depends(get_user_from_token), db: Session = Depends(get_db)):
    user_id = UUID(user["sub"])
    db_user = get_user_by_id(db, user_id)
    
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found in database")
    
    return {
        "id": str(db_user.id),
        "username": db_user.username,
        "email": db_user.email,
        "created_at": db_user.created_at,
    }