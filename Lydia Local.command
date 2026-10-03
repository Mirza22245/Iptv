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

echo "Starting Lydia locally..."
docker compose -f docker-compose.local.yml up -d --build

echo "Waiting for Lydia..."
for i in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

open http://localhost:3000

echo ""
echo "Lydia is running: http://localhost:3000"
echo "API: http://localhost:8000/docs"
echo "Close this window when you are done, or use: docker compose -f docker-compose.local.yml down"
