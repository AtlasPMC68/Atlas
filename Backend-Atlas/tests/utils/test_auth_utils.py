from app.utils.auth import hash_password, verify_password, create_access_token
from jose import jwt
from datetime import datetime, timezone

SECRET_KEY = "ton_secret_ultra_secret"
ALGORITHM = "HS256"

def test_hash_password_and_verify():
    password = "securepassword123"
    hashed = hash_password(password)

    assert verify_password(password, hashed)
    assert not verify_password("wrongpassword", hashed)

def test_create_access_token_structure():
    user_id = "test_user"
    token = create_access_token(user_id)

    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    
    assert payload["sub"] == user_id
    assert "exp" in payload

    exp = datetime.fromtimestamp(payload["exp"], timezone.utc)
    assert exp > datetime.now(timezone.utc)

def test_token_expiry():
    user_id = "test_user"
    token = create_access_token(user_id)

    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], timezone.utc)

    assert exp > datetime.now(timezone.utc)