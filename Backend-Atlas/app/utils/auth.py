from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ..keycloak import verify_token

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

def get_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)):    
    token_info = verify_token(credentials.credentials)
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid token or expired")
    
    realm_access = token_info.get("realm_access") or {}
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    return {
        "sub": token_info.get("sub"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
        "roles": set(roles),
    }

def get_optional_user_from_token(credentials: HTTPAuthorizationCredentials | None = Depends(optional_security)):
    if credentials is None:
        return None
    token_info = verify_token(credentials.credentials)
    if not token_info:
        return None
    
    realm_access = token_info.get("realm_access") or {}
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    return {
        "sub": token_info.get("sub"),
        "email": token_info.get("email"),
        "preferred_username": token_info.get("preferred_username"),
        "roles": set(roles),
    }


def require_admin_user(user: dict = Depends(get_user_from_token)) -> dict:
    """Autorise uniquement les utilisateurs possédant le rôle Keycloak admin."""
    if "admin" not in user.get("roles", set()):
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user

def get_current_user_id(user: dict = Depends(get_user_from_token)) -> str:
    return user["sub"]

def get_optional_user_id(user: dict | None = Depends(get_optional_user_from_token)) -> str | None:
    return user["sub"] if user else None
