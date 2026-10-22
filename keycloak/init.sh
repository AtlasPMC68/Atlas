#!/bin/bash

# Compile template if envsubst was not run on host
if [ -f /var/tmp/atlas-frontend.json.template ] && [ -w /var/tmp/atlas-frontend.json ]; then
  APP_URL="${APP_BASE_URL:-http://localhost}"
  echo "Preparing atlas-frontend.json for ${APP_URL}..."
  sed "s|\${APP_BASE_URL}|${APP_URL}|g; s|\${DOMAIN}|${DOMAIN:-localhost}|g" \
    /var/tmp/atlas-frontend.json.template > /var/tmp/atlas-frontend.json
fi

# start-dev locally, start (production mode) on the server via KC_START_MODE
KC_START_MODE="${KC_START_MODE:-start-dev}"
echo "Starting Keycloak in background (${KC_START_MODE})..."
/opt/keycloak/bin/kc.sh "$KC_START_MODE" --http-port 8080 --http-relative-path=/auth &

KEYCLOAK_PID=$!

echo "Waiting for Keycloak to be ready..."
while ! (echo > /dev/tcp/localhost/8080) 2>/dev/null; do
  echo "Keycloak not ready yet..."
  sleep 2
done

echo "Keycloak ready!"
echo "Running Keycloak configuration..."
/var/tmp/setdata.sh

wait $KEYCLOAK_PID
