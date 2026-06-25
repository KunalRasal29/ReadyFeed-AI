#!/bin/sh
set -e

wait_for_host() {
  name="$1"
  host="$2"
  port="$3"

  if [ -z "$host" ] || [ -z "$port" ]; then
    return 0
  fi

  echo "Waiting for $name at $host:$port..."
  python - "$host" "$port" <<'PY'
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
deadline = time.time() + 60

while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(1)

print(f"Timed out waiting for {host}:{port}", file=sys.stderr)
sys.exit(1)
PY
}

wait_for_host "PostgreSQL" "$POSTGRES_HOST" "$POSTGRES_PORT"
wait_for_host "Redis" "$REDIS_HOST" "$REDIS_PORT"

if [ "$RUN_MIGRATIONS" = "true" ]; then
  python manage.py migrate --noinput
fi

if [ "$SEED_DEFAULTS" = "true" ]; then
  python manage.py seed_defaults
fi

exec "$@"
