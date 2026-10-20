#!/bin/bash

# Credentials come from the container environment (see .env / docker-compose.yml)
echo "Configuring Keycloak..."
# The port opens before the admin user is bootstrapped, so retry the login
for attempt in $(seq 1 30); do
  if /opt/keycloak/bin/kcadm.sh config credentials \
    --server http://localhost:8080/auth \
    --realm master \
    --user "${KEYCLOAK_ADMIN:-admin}" \
    --password "${KEYCLOAK_ADMIN_PASSWORD:-admin}"; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "ERROR: could not log in as Keycloak admin. Does KEYCLOAK_ADMIN_PASSWORD match the existing keycloak-data volume?"
    exit 1
  fi
  echo "Admin login failed (attempt $attempt/30), retrying in 5s..."
  sleep 5
done

# Create realm if it doesn't exist
echo "Creating realm atlas..."
if /opt/keycloak/bin/kcadm.sh get realms/atlas >/dev/null 2>&1; then
  echo "Realm atlas already exists"
else
  /opt/keycloak/bin/kcadm.sh create realms -s realm=atlas -s enabled=true -o
fi

echo "Setting Atlas login theme..."

/opt/keycloak/bin/kcadm.sh update realms/atlas \
  -s loginTheme=atlas
  
# Update realm settings
# REALM_SSL_REQUIRED is "external" on the server, "none" for plain-HTTP local dev
echo "Updating realm settings..."
/opt/keycloak/bin/kcadm.sh update realms/atlas \
  -s registrationAllowed=true \
  -s loginWithEmailAllowed=true \
  -s resetPasswordAllowed=true \
  -s sslRequired="${REALM_SSL_REQUIRED:-none}" \
  -s accessTokenLifespan=3600 \
  -s ssoSessionMaxLifespan=86400 \
  -s ssoSessionIdleTimeout=3600 

# Function to check if client exists
client_exists() {
  local client_id=$1
  /opt/keycloak/bin/kcadm.sh get clients -r atlas -q clientId="$client_id" --fields id | grep -q "id"
}

# Create or update frontend client
echo "Setting up frontend client..."
if client_exists "atlas-frontend"; then
  echo "Frontend client already exists, updating configuration..."
  FRONTEND_CLIENT_ID=$(/opt/keycloak/bin/kcadm.sh get clients -r atlas -q clientId=atlas-frontend --fields id | grep -oP '(?<="id" : ")[^"]*')
  /opt/keycloak/bin/kcadm.sh update clients/"$FRONTEND_CLIENT_ID" -r atlas -f /var/tmp/atlas-frontend.json
  echo "Frontend client updated"
else
  /opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-frontend.json
  echo "Frontend client created"
fi

# Create backend client if it doesn't exist, and keep its secret in sync with .env
echo "Setting up backend client..."
if client_exists "atlas-backend"; then
  BACKEND_CLIENT_ID=$(/opt/keycloak/bin/kcadm.sh get clients -r atlas -q clientId=atlas-backend --fields id | grep -oP '(?<="id" : ")[^"]*')
  /opt/keycloak/bin/kcadm.sh update clients/"$BACKEND_CLIENT_ID" -r atlas -s secret="${KEYCLOAK_CLIENT_SECRET:-secret}"
  echo "Backend client already exists, secret updated"
else
  /opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-backend.json -s secret="${KEYCLOAK_CLIENT_SECRET:-secret}"
  echo "Backend client created"
fi

# Add 'sub' mapper to frontend client
echo "Adding 'sub' claim mapper to atlas-frontend..."
FRONTEND_CLIENT_ID=$(/opt/keycloak/bin/kcadm.sh get clients -r atlas -q clientId=atlas-frontend --fields id | grep -oP '(?<="id" : ")[^"]*')

if [ -n "$FRONTEND_CLIENT_ID" ]; then
  echo "Frontend client UUID: $FRONTEND_CLIENT_ID"
  
  # Create a User Property mapper for 'sub' claim
  /opt/keycloak/bin/kcadm.sh create clients/$FRONTEND_CLIENT_ID/protocol-mappers/models -r atlas -s name=user-id-mapper -s protocol=openid-connect -s protocolMapper=oidc-usermodel-property-mapper -s 'config."user.attribute"=id' -s 'config."claim.name"=sub' -s 'config."jsonType.label"=String' -s 'config."id.token.claim"=true' -s 'config."access.token.claim"=true' -s 'config."userinfo.token.claim"=true'
  
  echo "Mapper 'sub' added to frontend client"
else
  echo "Error: Could not find frontend client UUID"
fi

echo "Keycloak configuration finished"