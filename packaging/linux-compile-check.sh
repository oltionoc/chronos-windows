#!/bin/sh
# Compile chronos-server and chronos-worker with Nuitka on Linux, inside a
# throwaway container, using exactly the flags the Windows build uses
# (packaging/nuitka/*.args).
#
# Why this exists: Nuitka cannot cross-compile, so the real Windows
# executables can only be built on Windows. But almost everything that goes
# wrong in a compiled Python program — a module loaded by name at run time, a
# missing data file, missing package metadata — goes wrong identically on
# every platform. Compiling and running here catches those before a Windows
# build ever runs.
#
#   ./packaging/linux-compile-check.sh
#
# Output: packaging/build-linux/{server,worker}/ (git-ignored).
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/packaging/build-linux"
# Same version as packaging/windows/build.ps1 (verified by both builds).
NUITKA_VERSION=${NUITKA_VERSION:-4.2.1}

args_of() {
    grep -v '^[[:space:]]*#' "$ROOT/packaging/nuitka/$1.args" | grep -v '^[[:space:]]*$' | tr '\n' ' '
}

SERVER_ARGS=$(args_of server)
WORKER_ARGS=$(args_of worker)

# Under WSL the `docker` command is often Docker Desktop's Windows client,
# which reads bind-mount sources as Windows paths; compose translates them,
# a plain `docker run` does not. wslpath gives the \\wsl.localhost\... form.
host_path() {
    if command -v wslpath >/dev/null 2>&1; then wslpath -w "$1"; else printf '%s' "$1"; fi
}

mkdir -p "$OUT" "$OUT/.cache"
docker run --rm \
    -v "$(host_path "$ROOT"):/src:ro" \
    -v "$(host_path "$OUT"):/out" \
    -v "$(host_path "$OUT/.cache"):/root/.cache" \
    -e SERVER_ARGS="$SERVER_ARGS" \
    -e WORKER_ARGS="$WORKER_ARGS" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
    python:3.12-bookworm sh -eu -c '
        apt-get update -qq && apt-get install -y -qq patchelf ccache >/dev/null
        if [ -n "'"$NUITKA_VERSION"'" ]; then pip install -q "nuitka=='"$NUITKA_VERSION"'"; else pip install -q nuitka; fi
        pip install -q ordered-set zstandard
        pip show nuitka | grep "^Version"

        # Copy sources without local virtualenvs, caches or tests.
        for d in backend worker; do
            mkdir -p "/build-$d"
            (cd "/src/$d" && tar --exclude=./.venv --exclude="__pycache__" --exclude=./tests -cf - .) | tar -C "/build-$d" -xf -
        done

        cd /build-backend
        pip install -q -r requirements.txt
        python -m nuitka $SERVER_ARGS --output-dir=/tmp/server --assume-yes-for-downloads chronos_server.py

        cd /build-worker
        pip install -q -r requirements.txt
        python -m nuitka $WORKER_ARGS --output-dir=/tmp/worker --assume-yes-for-downloads chronos_worker.py

        rm -rf /out/server /out/worker
        cp -r /tmp/server/chronos_server.dist /out/server
        cp -r /tmp/worker/chronos_worker.dist /out/worker
        chown -R "$HOST_UID:$HOST_GID" /out
    '

echo
echo "compiled:"
ls -la "$OUT/server/chronos-server" "$OUT/worker/chronos-worker"
echo "python source files in the server build (should be only the migrations):"
find "$OUT/server" -name '*.py' | sed "s|$OUT/server/||" | sort
