#!/usr/bin/env bash
# One-command local reproduction; no server, publishing or active build invocation.
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$HERE/../.." && pwd)"
if [[ ! -x "$HERE/.venv/bin/python" ]]; then
  python3 -m venv "$HERE/.venv"
fi
"$HERE/.venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements.txt"
"$HERE/.venv/bin/python" "$HERE/probe.py"
