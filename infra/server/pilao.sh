#!/usr/bin/env bash
# docker compose for this deployment, with the images deploy.sh last put in service.
#   ./pilao.sh ps            ./pilao.sh logs -f api worker
#   ./pilao.sh exec postgres psql -U pilao
#   ./pilao.sh exec api python -m app.cli feedback-report --days 7
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -f release.env ]; then
  echo "No release.env: nothing deployed yet (push to GitHub, or run the Deploy workflow)." >&2
  exit 1
fi
set -a
. ./release.env
set +a
exec docker compose -f docker-compose.yml "$@"
