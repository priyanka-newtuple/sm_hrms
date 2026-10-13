#!/usr/bin/env bash
set -euo pipefail
umask 077
sha=${1:?Release SHA required}
[[ "$sha" =~ ^[a-f0-9]{40}$ ]] || exit 2
base=/opt/newtuple-hrms
release="$base/releases/$sha"
cd "$release"
exec 9>"$base/deploy.lock"
flock -n 9 || { echo 'Another HRMS deployment is running'; exit 1; }
test -f "$base/production.env"
sha256sum -c SHA256SUMS
export IMAGE_TAG="$sha"
compose=(docker compose --project-name newtuple-hrms-production --env-file "$base/production.env" -f "$release/compose.yml")
"${compose[@]}" config --quiet
# Only images in this release are loaded. No global prune, stop, or compose down.
gzip -dc images.tar.gz | docker load
"${compose[@]}" up -d --wait --wait-timeout 120 platform-db hrms-app-db platform-redis
mkdir -p "$base/backups"
backup="$base/backups/$(date -u +%Y%m%dT%H%M%SZ)-$sha"
mkdir "$backup"
for service in platform-db hrms-app-db; do
  id=$("${compose[@]}" ps -q "$service")
  if [[ -n "$id" ]]; then
    "${compose[@]}" exec -T "$service" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$backup/$service.sql.gz"
    gzip -t "$backup/$service.sql.gz"
  fi
done
# Migrations may run at platform startup. Do not automatically roll back schemas.
trap 'echo "Deployment failed. Previous release pointer retained. Inspect HRMS only; database restore requires an explicit recovery decision." >&2' ERR
# Preserve files written by the native default local provider before replacing its container.
# The existing uploads volume is retained across releases; never delete or move source files.
current_api=$("${compose[@]}" ps -q platform-api)
if [ -n "$current_api" ]; then
  docker exec "$current_api" sh -c '
    if [ -d /tmp/modular_filehandler ]; then
      mkdir -p /app/backend/uploads/native-files
      cp -an /tmp/modular_filehandler/. /app/backend/uploads/native-files/
    fi'
fi
"${compose[@]}" up -d --no-deps --wait --wait-timeout 300 platform-api
"${compose[@]}" run --rm --no-deps platform-install
"${compose[@]}" up -d --no-deps --wait --wait-timeout 180 hrms-app platform-web
"${compose[@]}" exec -T platform-web wget -q -O /dev/null http://127.0.0.1/health
"${compose[@]}" exec -T platform-web wget -q -O /dev/null http://127.0.0.1/login
"${compose[@]}" run --rm --no-deps platform-install python -m hrms_app.verify_native_setup
if [[ -L "$base/current" ]]; then
  readlink "$base/current" > "$base/previous-release"
fi
ln -sfn "$release" "$base/current"
echo "HRMS release $sha is healthy."
