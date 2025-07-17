import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db import get_db
from ..models.user import User
from ..utils.auth import get_current_user

router = APIRouter()

USERNAME_REGEX = r"^[a-zA-Z0-9!\-_\$\%\*]+$"
USERNAME_MAX_LENGTH = 20
USERNAME_MIN_LENGTH = 3

@router.put("/user/update-user")
def update_username(data: dict, user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    new_username = data.get("username")
    if not new_username:
        raise HTTPException(status_code=400, detail="Nom d'utilisateur requis")
    
    if len(new_username) > USERNAME_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Le nom d'utilisateur doit contenir au plus {USERNAME_MAX_LENGTH} caractères")

    if len(new_username) < USERNAME_MIN_LENGTH:
        raise HTTPException(status_code=400, detail=f"Le nom d'utilisateur doit contenir au moins {USERNAME_MIN_LENGTH} caractères")

    if not re.match(USERNAME_REGEX, new_username):
        raise HTTPException(
            status_code=400,
            detail="Le nom d'utilisateur ne peut contenir que des lettres, chiffres, et les caractères spéciaux ! - _ $ % *"
        )
    
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
