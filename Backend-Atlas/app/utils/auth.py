from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..keycloak import verify_token

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    
    if ',' in token:
        token = token.split(',')[0]
    
    if token.count('.') != 2:
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token_info = verify_token(token)
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