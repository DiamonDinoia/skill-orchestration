#!/usr/bin/env bash
# Install hermes-dispatch-route to ~/.local/bin from this release tree. A copy, never a symlink.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/skills/tiered-subagent-dispatch/scripts/hermes-dispatch-route"
DST="${HOME:?install.sh: HOME is not set}/.local/bin/hermes-dispatch-route"

# Pass 1: load and validate the source, so a bad shape cannot leave a partial install behind.
[ -f "$SRC" ] || { echo "install.sh: $SRC: not found; refusing to write" >&2; exit 2; }
python3 -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "$SRC" \
    || { echo "install.sh: $SRC: does not compile; refusing to write" >&2; exit 2; }

# Pass 2: copy with a timestamped backup of the file already installed.
mkdir -p "$(dirname "$DST")"
if [ -f "$DST" ] && cmp -s "$SRC" "$DST"; then
    echo "SKIP  $DST (identical)"
    exit 0
fi
if [ -e "$DST" ]; then
    cp -p "$DST" "$DST.bak.$(date -u +%Y%m%d%H%M%S)"
fi
cp --remove-destination "$SRC" "$DST"
chmod 755 "$DST"
echo "WROTE $DST"
