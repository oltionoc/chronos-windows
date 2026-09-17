#!/bin/sh
# Build and push the three chronos images to a private registry.
#
#   REGISTRY=docker.io/<your-user> ./ops/release.sh beta
#   REGISTRY=ghcr.io/<your-github-user> ./ops/release.sh 1.0.0
#
# Run it from the project root (the folder holding docker-compose.yml). The
# client's machine never builds anything — it pulls what this script pushes,
# which is what keeps the source off their PC.
set -eu

TAG=${1:-beta}
: "${REGISTRY:?Set REGISTRY first, e.g. REGISTRY=docker.io/yourname}"

for svc in api worker frontend; do
    case "$svc" in
        api) context=./backend ;;
        worker) context=./worker ;;
        frontend) context=./frontend ;;
    esac
    image="$REGISTRY/chronos-$svc:$TAG"
    echo "==> building $image"
    docker build -t "$image" "$context"
    echo "==> pushing $image"
    docker push "$image"
done

echo
echo "Pushed with tag: $TAG"
echo "On the client machine: set TAG=$TAG in .env, then"
echo "  docker compose pull && docker compose up -d"
