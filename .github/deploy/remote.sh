# Runs on the VPS (ssh ... bash -s), after the workflow copied /tmp/server-nex.tar.gz and /tmp/server.tar.gz.
# Updates the tracked files of server/ in place: .env, data/ and the Docker volumes are not touched.
set -euo pipefail
cd /opt/dqmj3p

# Keep the running image to roll back to (docs/deploy.md)
docker tag server-nex:latest server-nex:previous
gunzip -c /tmp/server-nex.tar.gz | docker load

tar -xzf /tmp/server.tar.gz --no-same-owner
chmod -R a+rX server/sil server/spotpass server/nncs server/nex/sql
rm -f /tmp/server-nex.tar.gz /tmp/server.tar.gz

cd server
# sil, spotpass and nncs read their code from a bind mount: recreate them to load it
docker compose up -d --no-build --remove-orphans </dev/null
docker compose up -d --no-build --force-recreate sil spotpass nncs </dev/null

sleep 10
failed=0
for service in postgres nex sil spotpass nncs; do
    state=$(docker compose ps --format '{{.State}}' "$service" </dev/null)
    echo "$service: $state"
    [ "$state" = running ] || failed=1
done
seed=$(docker inspect -f '{{.State.ExitCode}}' server-seed-1 2>/dev/null || echo missing)
echo "seed exit code: $seed"
[ "$seed" = 0 ] || failed=1
curl -fsS -o /dev/null http://127.0.0.1:8380/p01/nsa/H7btVjYWs7p5dGj6/FGONLYT/BossPresentDisc.bin || { echo "spotpass not answering"; failed=1; }
docker image prune -f >/dev/null
exit $failed
