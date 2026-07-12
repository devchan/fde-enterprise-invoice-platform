# syntax=docker/dockerfile:1

# ---- Shared dependency layer ----
FROM node:20.18.1-bookworm-slim AS deps
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/.npmrc ./
RUN npm ci --no-audit --no-fund --fetch-timeout=600000 --fetch-retries=5

# ---- Development server (hot reload) — target used by docker-compose.yml ----
FROM deps AS dev
ENV NODE_ENV=development
COPY frontend ./
EXPOSE 3000
CMD ["npm", "run", "dev"]

# ---- Production build ----
FROM deps AS build
ENV NODE_ENV=production
# API base URL is baked into the static bundle at build time; override per environment.
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY frontend ./
RUN npm run build

# ---- Production runtime: static assets served by non-root nginx ----
FROM nginxinc/nginx-unprivileged:1.27-alpine AS production
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 8080
