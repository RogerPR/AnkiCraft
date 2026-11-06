#!/usr/bin/env bash
# Build release files into dist/:
#   dist/AnkiCraft-<version>.zip                 -> upload to CurseForge
#   dist/ankicraft_bridge-<version>.ankiaddon    -> upload to AnkiWeb
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^## Version: *//p' AnkiCraft/AnkiCraft.toc | tr -d '\r')
BRIDGE_VERSION=$(sed -n 's/^BRIDGE_VERSION = "\(.*\)"/\1/p' anki-addon/ankicraft_bridge/exporter.py)
if [[ "$VERSION" != "$BRIDGE_VERSION" ]]; then
  echo "warning: addon version $VERSION != bridge version $BRIDGE_VERSION" >&2
fi

echo "Running tests..."
luajit tests/lua/run.lua >/dev/null
if [[ -x .venv/bin/python ]]; then .venv/bin/python -m pytest -q tests/python >/dev/null; fi

rm -rf dist && mkdir -p dist

# CurseForge: the zip must contain the AnkiCraft/ folder at its root.
zip -qr "dist/AnkiCraft-$VERSION.zip" AnkiCraft -x '*.DS_Store'

# AnkiWeb: the .ankiaddon is a zip of the add-on folder's *contents*.
(cd anki-addon/ankicraft_bridge && zip -qr "../../dist/ankicraft_bridge-$BRIDGE_VERSION.ankiaddon" . \
  -x '__pycache__/*' '*/__pycache__/*' 'meta.json' 'user_files/*' '*.DS_Store')

ls -la dist
