#!/usr/bin/env bash
# wait-for-it.sh — wait until a TCP host:port is available
set -e
HOST="$1"
PORT="$2"
TIMEOUT="${3:-30}"
echo "Waiting for $HOST:$PORT (timeout ${TIMEOUT}s)..."
for i in $(seq 1 "$TIMEOUT"); do
  if nc -z "$HOST" "$PORT" 2>/dev/null; then
    echo "$HOST:$PORT is available after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "Timed out waiting for $HOST:$PORT"
exit 1

