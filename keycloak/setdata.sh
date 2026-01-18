#!/bin/bash

echo "Configuring Keycloak..."
/opt/keycloak/bin/kcadm.sh config credentials \
  --server http://localhost:8080 \
  --realm master \
  --user admin \
  --password admin

/opt/keycloak/bin/kcadm.sh create realms -s realm=atlas -s enabled=true -o \
  || echo "Realm atlas already exists"

/opt/keycloak/bin/kcadm.sh update realms/atlas \
  -s registrationAllowed=true \
  -s loginWithEmailAllowed=true

/opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-frontend.json \
  || echo "Frontend client already exists"

/opt/keycloak/bin/kcadm.sh create clients -r atlas -f /var/tmp/atlas-backend.json \
  || echo "Backend client already exists"

echo "Keycloak configuration finished"