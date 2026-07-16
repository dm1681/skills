#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if command -v uv >/dev/null 2>&1; then
  exec uv run --project "$SCRIPT_DIR" --python 3.12 "$SCRIPT_DIR/install.py" "$@"
fi

if command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/install.py" "$@"
fi

if command -v python >/dev/null 2>&1 \
  && python -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
  exec python "$SCRIPT_DIR/install.py" "$@"
fi

printf '%s\n' 'uv or Python 3.9 or newer is required.' >&2
exit 127
