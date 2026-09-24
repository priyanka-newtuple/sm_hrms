FROM node:22-alpine AS base
WORKDIR /app

# Customer skins — empty by default so a bare `docker build` stays vanilla.
# A deployment's compose file overrides this named context with a real skins
# directory via build.additional_contexts (see docker-compose.prod.yml).
FROM scratch AS customer-skins

# Build context is the repo root (see docker-compose.prod.yml), so paths are
# prefixed with frontend/. The repo-root changelogs/ dir is copied to /changelogs
# so the What's New page's import.meta.glob('../../../../changelogs/*.mdx') resolves.
FROM base AS deps
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

FROM deps AS builder
COPY frontend/ ./
COPY changelogs/ /changelogs/
# Under /app so skin bare imports resolve against /app/node_modules at build.
# Skin tsconfig.json files are editor-only and reference host paths that do
# not exist in the image — esbuild would fail resolving their `extends`.
COPY --from=customer-skins / /app/customer-skins/
RUN rm -f /app/customer-skins/tsconfig.json /app/customer-skins/*/tsconfig.json

ARG VITE_BYPASS_AUTH=false
ARG VITE_GOOGLE_CLIENT_ID=
ARG VITE_API_BASE_URL=/api
# Skin selection — passed by compose from the deployment .env. Defaults are
# the platform's own skin/stub so a bare `docker build` stays vanilla.
# Customer skin dirs under frontend/customer-skins/ ride in via COPY frontend/ above.
ARG VITE_SKIN_ID=state-machine
ARG CUSTOMER_SKINS_PATH=/app/src/skins/customer-skins.stub.ts
ARG VITE_SKIN_API_URL=
ARG VITE_HIDE_KANBAN=false
ARG VITE_HIDE_DASHBOARD=false
ARG VITE_HIDE_AGENT=false
ARG VITE_HIDE_TASKS=false
ARG VITE_HIDE_RECORDS=false

ENV VITE_BYPASS_AUTH=$VITE_BYPASS_AUTH
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_SKIN_API_URL=$VITE_SKIN_API_URL
ENV VITE_HIDE_KANBAN=$VITE_HIDE_KANBAN
ENV VITE_HIDE_DASHBOARD=$VITE_HIDE_DASHBOARD
ENV VITE_HIDE_AGENT=$VITE_HIDE_AGENT
ENV VITE_HIDE_TASKS=$VITE_HIDE_TASKS
ENV VITE_HIDE_RECORDS=$VITE_HIDE_RECORDS

RUN npm run build

FROM base AS runner
ENV NODE_ENV=production

RUN npm install -g serve

COPY --from=builder /app/dist ./dist

EXPOSE 5111

CMD ["serve", "-s", "/app/dist", "-l", "5111"]