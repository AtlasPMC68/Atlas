#!/bin/bash

echo "Starting Keycloak in background..."
/opt/keycloak/bin/kc.sh start-dev --http-port 8080 &

# On récupère le PID du serveur
KEYCLOAK_PID=$!

echo "Waiting for Keycloak to be ready..."

# Boucle simple pour tester le port 8080
while ! (echo > /dev/tcp/localhost/8080) 2>/dev/null; do
  echo "Keycloak not ready yet..."
  sleep 2
done

echo "Keycloak ready!"

echo "Running Keycloak configuration..."
/var/tmp/setdata.sh

wait $KEYCLOAK_PID
