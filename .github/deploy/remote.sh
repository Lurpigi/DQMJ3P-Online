# Runs on the VPS (ssh ... bash -s), after the workflow copied /tmp/server-nex.tar.gz and /tmp/server.tar.gz.
# Updates the tracked files of server/ in place: .env, data/ and the Docker volumes are not touched.
set -euo pipefail
cd /opt/dqmj3p

# Keep the running image to roll back to (docs/deploy.md)
docker tag server-nex:latest server-nex:previous
docker tag server-dashboard:latest server-dashboard:previous 2>/dev/null || true
gunzip -c /tmp/server-nex.tar.gz | docker load   # server-nex and server-dashboard

tar -xzf /tmp/server.tar.gz --no-same-owner
chmod -R a+rX server/sil server/spotpass server/nncs server/nex/sql server/caddy
rm -f /tmp/server-nex.tar.gz /tmp/server.tar.gz

cd server
# sil, spotpass and nncs read their code from a bind mount: recreate them to load it
docker compose up -d --no-build --remove-orphans </dev/null
docker compose up -d --no-build --force-recreate sil spotpass nncs </dev/null
# The portal (profile "portal" in .env) reads sil_server.py from the same bind mount
portal=$(docker compose config --services </dev/null | grep -qx dashboard && echo 1 || echo 0)
[ "$portal" = 1 ] && docker compose up -d --no-build --force-recreate dashboard </dev/null

sleep 10
failed=0
services="postgres nex sil spotpass nncs"
[ "$portal" = 1 ] && services="$services dashboard caddy"
for service in $services; do
    state=$(docker compose ps --format '{{.State}}' "$service" </dev/null)
    echo "$service: $state"
    [ "$state" = running ] || failed=1
done
seed=$(docker inspect -f '{{.State.ExitCode}}' server-seed-1 2>/dev/null || echo missing)
echo "seed exit code: $seed"
[ "$seed" = 0 ] || failed=1
curl -fsS -o /dev/null http://127.0.0.1:8380/p01/nsa/H7btVjYWs7p5dGj6/FGONLYT/BossPresentDisc.bin || { echo "spotpass not answering"; failed=1; }
if [ "$portal" = 1 ]; then
    migrate=$(docker inspect -f '{{.State.ExitCode}}' server-dashboard-migrate-1 2>/dev/null || echo missing)
    echo "dashboard-migrate exit code: $migrate"
    [ "$migrate" = 0 ] || failed=1
    docker compose exec -T dashboard python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/api/v1/health', timeout=5)" </dev/null \
        || { echo "portal API not answering"; failed=1; }
fi
docker image prune -f >/dev/null
exit $failed
