from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..keycloak import verify_token

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):    
    token_info = verify_token(credentials.credentials)
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid token or expired")
    
    return {
        "sid": token_info.get("sid"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
        "token_info": token_info
    }

def get_current_user_id(user: dict = Depends(get_current_user)) -> str:
    return user["sid"]