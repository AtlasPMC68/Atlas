#!/bin/bash

# TODO Add real credentials for deployment
echo "Configuring Keycloak..."
/opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin \
  --password admin

# Create realm if it doesn't exist
echo "Creating realm atlas..."
if /opt/keycloak/bin/kcadm.sh get realms/atlas >/dev/null 2>&1; then
  echo "Realm atlas already exists"
else
  /opt/keycloak/bin/kcadm.sh create realms -s realm=atlas -s enabled=true -o
fi

# Update realm settings
# TODO remove sslRequired=None for production
echo "Updating realm settings..."
/opt/keycloak/bin/kcadm.sh update realms/atlas \
  -s registrationAllowed=true \
  -s loginWithEmailAllowed=true \
  -s sslRequired=None \
  -s accessTokenLifespan=3600 \
  -s ssoSessionMaxLifespan=86400 \
  -s ssoSessionIdleTimeout=3600

# Function to check if client exists
client_exists() {
  local client_id=$1
  /opt/keycloak/bin/kcadm.sh get clients -r atlas -q clientId="$client_id" --fields id | grep -q "id"
}

# Create frontend client if it doesn't exist
echo "Setting up frontend client..."
if client_exists "atlas-frontend"; then
  echo "Frontend client already exists"
else
  /opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-frontend.json
  echo "Frontend client created"
fi

# Create backend client if it doesn't exist
echo "Setting up backend client..."
if client_exists "atlas-backend"; then
  echo "Backend client already exists"
else
  /opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-backend.json
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