# ── Stage 1: build the SPA ────────────────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Served from the same origin as the API in production, so a relative base URL
# means no CORS and no rebuild when the host changes.
ARG VITE_API_URL=/app
ENV VITE_API_URL=$VITE_API_URL
# Vite inlines env at build time, so the Google client id has to arrive here
# rather than at run time. It is a public identifier, not a secret.
ARG VITE_GOOGLE_CLIENT_ID=""
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

# ── Stage 2: serve it, and front the API ──────────────────────────────────────
FROM caddy:2.8-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
