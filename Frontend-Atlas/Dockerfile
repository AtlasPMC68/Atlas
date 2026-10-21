# Development stage for Vite Frontend Application
FROM node:20.20.2-alpine AS development

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "--port", "5173"]

# Build stage: VITE_* values are baked into the bundle at build time
FROM node:20.20.2-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_URL
ARG VITE_KEYCLOAK_URL
ARG VITE_KEYCLOAK_REALM
ARG VITE_KEYCLOAK_CLIENT_ID
ARG VITE_CARTO_API_KEY
ARG VITE_ENABLE_DEV_TOOLS=false

# Type check + build: a type error fails the image build
RUN npm run build

# Production stage: static files only, no Node at runtime
FROM caddy:2.11.4-alpine AS production

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv

EXPOSE 5173
