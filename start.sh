#!/bin/sh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.9 or newer is required. Install Python 3 and try again." >&2
    exit 1
fi
if ! python3 -c 'import sys, sqlite3; sys.exit(sys.version_info < (3, 9))'; then
    echo "Python 3.9 or newer with SQLite support is required." >&2
    exit 1
fi
exec python3 -X utf8 -B app.py "$@"
