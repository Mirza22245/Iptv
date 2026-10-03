#!/bin/zsh
set -e
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed. Install Docker Desktop first."
  read -n 1
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Start Docker Desktop and run this file again."
  read -n 1
  exit 1
fi

echo "Starting Lydia local database..."

# The local compose stack expects PostgreSQL on localhost:5432. Reuse an
# existing lydia-postgres container when present; otherwise create one with a
# persistent named volume. Removing a container does not remove its volume.
if docker container inspect lydia-postgres >/dev/null 2>&1; then
  docker start lydia-postgres >/dev/null 2>&1 || true
else
  docker run -d \
    --name lydia-postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=lydia \
    -p 5432:5432 \
    -v lydia_postgres_data:/var/lib/postgresql/data \
    postgres:16 >/dev/null
fi

for i in {1..30}; do
  if docker exec lydia-postgres pg_isready -U postgres -d lydia >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec lydia-postgres pg_isready -U postgres -d lydia >/dev/null 2>&1; then
  echo "PostgreSQL did not become ready."
  exit 1
fi

echo "Applying database schema and local test data..."
docker exec -i lydia-postgres psql -v ON_ERROR_STOP=1 -U postgres -d lydia < database/init/00-create-role.sql
docker exec -i lydia-postgres psql -v ON_ERROR_STOP=1 -U postgres -d lydia < database/schema_v2.sql
docker exec -i lydia-postgres psql -v ON_ERROR_STOP=1 -U postgres -d lydia < database/init/20-grants.sql
docker exec -i lydia-postgres psql -v ON_ERROR_STOP=1 -U postgres -d lydia < database/local_seed.sql

echo "Starting Lydia backend and web..."
docker compose -f docker-compose.local.yml up -d --build

echo "Waiting for Lydia..."
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  echo "Lydia API did not become ready."
  docker compose -f docker-compose.local.yml logs --tail=80 backend || true
  exit 1
fi

open http://localhost:3000

echo ""
echo "Lydia is running: http://localhost:3000"
echo "API: http://localhost:8000/docs"
echo ""
echo "Local test users:"
echo "  Admin:    admin@lydia.local / Admin123456!"
echo "  Staff:    staff@lydia.local / Staff123456!"
echo "  Customer: customer@lydia.local / Customer123456!"
echo ""
echo "Close this window when you are done, or use: docker compose -f docker-compose.local.yml down"
