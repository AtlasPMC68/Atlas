from sqlalchemy.orm import Session
from uuid import UUID
from ..models.user import User
from fastapi import HTTPException

def create_user(db: Session, user_id: UUID, email: str, username: str) -> User:
    """Create a new user in the database"""
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

def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    """Get user by ID from the database"""
    return db.query(User).filter(User.id == user_id).first()
