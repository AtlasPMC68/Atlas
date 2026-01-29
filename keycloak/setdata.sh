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
echo "Updating realm settings..."
/opt/keycloak/bin/kcadm.sh update realms/atlas \
  -s registrationAllowed=true \
  -s loginWithEmailAllowed=true

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

echo "Keycloak configuration finished"