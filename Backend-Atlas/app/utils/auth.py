from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..keycloak import verify_token

security = HTTPBearer()

def get_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):    
    token_info = verify_token(credentials.credentials)
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid token or expired")
    
    return {
        "sub": token_info.get("sub"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
    }

def get_current_user_id(user: dict = Depends(get_user_from_token)) -> str:
    return user["sub"]
