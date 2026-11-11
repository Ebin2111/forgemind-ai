# syntax=docker/dockerfile:1.7
#
# ForgeMind AI frontend (Next.js, standalone output).
# Build context is the frontend/ folder:
#   docker build -t forgemind-frontend --build-arg NEXT_PUBLIC_API_URL=http://localhost:8000 frontend
#
# NEXT_PUBLIC_API_URL is compiled into the browser bundle at build time, so it must be the URL
# the USER'S BROWSER can reach the API at (not the internal Docker service name).

ARG NODE_VERSION=22

# ------------------------------------------------------------------------------
# Stage 1: install dependencies from the lockfile
# ------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# ------------------------------------------------------------------------------
# Stage 2: build
# ------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .
# `public/` is optional in this project; make sure the COPY in the next stage always has a source.
RUN mkdir -p public && npm run build

# ------------------------------------------------------------------------------
# Stage 3: minimal runtime, non-root
# ------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup -S -g 10001 app && adduser -S -u 10001 -G app app

COPY --from=builder --chown=app:app /app/public ./public
COPY --from=builder --chown=app:app /app/.next/standalone ./
COPY --from=builder --chown=app:app /app/.next/static ./.next/static

USER app
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]