#!/usr/bin/env bash
set -e
PORT=${1:-8080}
cd "$(dirname "$0")"
python3 server.py "$PORT"
