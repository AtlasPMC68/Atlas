from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..keycloak import verify_token

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

def get_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):    
    token_info = verify_token(credentials.credentials)
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid token or expired")
    
    return {
        "sub": token_info.get("sub"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
    }

def get_optional_user_from_token(credentials: HTTPAuthorizationCredentials | None = Depends(optional_security)):
    if credentials is None:
        return None
    token_info = verify_token(credentials.credentials)
    if not token_info:
        return None
    
    return {
        "sub": token_info.get("sub"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
    }

def get_current_user_id(user: dict = Depends(get_user_from_token)) -> str:
    return user["sub"]

def get_optional_user_id(user: dict | None = Depends(get_optional_user_from_token)) -> str | None:
    return user["sub"] if user else None
