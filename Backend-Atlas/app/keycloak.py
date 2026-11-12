from keycloak import KeycloakOpenID
from dotenv import load_dotenv
import os
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError, JWTClaimsError
import textwrap


load_dotenv(dotenv_path=".env.dev")

raw_server_url = os.getenv("KEYCLOAK_URL", "http://keycloak:8080/auth/")
server_url = raw_server_url.rstrip("/") + "/"

keycloak_open_id = KeycloakOpenID(
    server_url=server_url,
    client_id=os.getenv("KEYCLOAK_CLIENT_ID"),
    realm_name=os.getenv("KEYCLOAK_REALM"),
    client_secret_key=os.getenv("KEYCLOAK_CLIENT_SECRET"),
)

def format_public_key(raw_key: str) -> str:
    wrapped = "\n".join(textwrap.wrap(raw_key, 64))
    return f"-----BEGIN PUBLIC KEY-----\n{wrapped}\n-----END PUBLIC KEY-----"

KEYCLOAK_ISSUER = os.getenv("KEYCLOAK_ISSUER")
KEYCLOAK_AUDIENCE = os.getenv("KEYCLOAK_AUDIENCE", "atlas-backend")

# Cached so we don't call Keycloak on every request; refreshed if the signing key rotates
_public_key = None

def get_keycloak_public_key(refresh: bool = False):
    global _public_key
    if _public_key is None or refresh:
        _public_key = format_public_key(keycloak_open_id.public_key())
    return _public_key

def _decode(token: str, key: str):
    return jwt.decode(
        token,
        key,
        algorithms=["RS256"],
        audience=KEYCLOAK_AUDIENCE,
        issuer=KEYCLOAK_ISSUER,
        options={"verify_iss": bool(KEYCLOAK_ISSUER)},
    )

def verify_token(token: str):
    try:
        try:
            payload = _decode(token, get_keycloak_public_key())
        except (ExpiredSignatureError, JWTClaimsError):
            raise
        except JWTError:
            # Signature failed: maybe Keycloak rotated its key, retry once with a fresh one
            payload = _decode(token, get_keycloak_public_key(refresh=True))
        if payload.get("azp") != os.getenv("KEYCLOAK_FRONT_END_CLIENT_ID"):
            print("Token not for this client")
            return None
        return payload
    except ExpiredSignatureError:
        print("Token expired")
        return None
    except JWTClaimsError as e:
        print(f"Invalid token claims: {e}")
        return None
    except JWTError:
        print("Invalid token")
        return None
