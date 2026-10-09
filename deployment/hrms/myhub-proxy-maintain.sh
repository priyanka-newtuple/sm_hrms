#!/usr/bin/env bash
set -euo pipefail
# Product-owned route restored after the shared edge container is recreated.
# Existing routes are never edited. Certificate renewal uses the existing
# repsolute-certbot cron / shared ACME volumes, including the MyHub certificate.
proxy=workout-app-frontend-1
base=/opt/newtuple-hrms/proxy
exec 9>"$base/maintain.lock"
flock -n 9 || exit 0
gateway=$(docker inspect --format '{{(index .NetworkSettings.Networks "workout-app_default").Gateway}}' "$proxy")
[[ "$gateway" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
sed "s/__HOST_GATEWAY__/$gateway/g" "$base/myhub-https.conf.template" > "$base/myhub.conf"
current=$(docker exec "$proxy" sh -c 'cat /etc/nginx/conf.d/myhub.conf 2>/dev/null' || true)
if [[ "$current" == "$(cat "$base/myhub.conf")" ]]; then exit 0; fi
docker exec "$proxy" nginx -t
printf '%s\n' "$current" > "$base/previous.conf"
docker cp "$base/myhub.conf" "$proxy:/etc/nginx/conf.d/myhub.conf"
if ! docker exec "$proxy" nginx -t; then
    docker cp "$base/previous.conf" "$proxy:/etc/nginx/conf.d/myhub.conf"
    exit 1
fi
docker exec "$proxy" nginx -s reload
