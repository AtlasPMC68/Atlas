from sqlalchemy.orm import Session
from uuid import UUID
from ..models.user import User
from fastapi import HTTPException

def get_or_create_user(db: Session, token_info: dict) -> User:
    user_id = UUID(token_info["sub"])
    email = token_info.get("email")
    username = token_info.get("preferred_username")
    user = db.query(User).filter((User.id == user_id) | (User.email == email)).first()

    if not user:
        user = User(
            id=user_id,
            username=username,
            email=email
        )
        db.add(user)
        try:
            db.commit()
            db.refresh(user)
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Cannot create user: {e}")
    return user
