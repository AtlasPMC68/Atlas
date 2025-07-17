from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models.user import User
from ..utils.auth import get_current_user

router = APIRouter()

@router.put("/user/update-user")
def update_username(data: dict, user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    new_username = data.get("username")
    if not new_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if user.username == new_username:
        return {"message": "No changes made, username is the same"}

    if db.query(User).filter(User.username == new_username).first():
        raise HTTPException(status_code=400, detail="Ce nom d’utilisateur est déjà pris")

    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    user.username = new_username
    db.commit()
    return {"message": "Username updated successfully", "username": user.username}
