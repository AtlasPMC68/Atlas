from keycloak import KeycloakOpenID
from dotenv import load_dotenv
import os
from jose import jwt, JWTError
import textwrap


load_dotenv(dotenv_path=".env.dev")

keycloak_open_id = KeycloakOpenID(
    server_url=os.getenv("KEYCLOAK_URL"),
    client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    realm_name=os.getenv("KEYCLOAK_REALM"),
    client_secret_key=os.getenv("KEYCLOAK_CLIENT_SECRET"),
)

def format_public_key(raw_key: str) -> str:
    wrapped = "\n".join(textwrap.wrap(raw_key, 64))
    return f"-----BEGIN PUBLIC KEY-----\n{wrapped}\n-----END PUBLIC KEY-----"

def get_keycloak_public_key():
    raw_key = keycloak_open_id.public_key()
    return format_public_key(raw_key)

def verify_token(token: str):
    try:
        key = get_keycloak_public_key()
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )
        if payload.get("azp") != os.getenv("KEYCLOAK_FRONT_END_CLIENT_ID"):
            print("Token not for this client")
            return None
        return payload
    except JWTError:
        print(f"Invalid token")
        return None
