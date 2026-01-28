#!/usr/bin/env bash
set -euo pipefail

TTY=${1:-/dev/tty1}

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root, e.g.: sudo $0" >&2
  exit 1
fi

# Derive tty name (e.g. /dev/tty1 -> tty1) and VT number (e.g. tty1 -> 1)
TTY_NAME="${TTY#/dev/}"
VT_NUM="${TTY_NAME#tty}"

if ! [[ "$VT_NUM" =~ ^[0-9]+$ ]]; then
  echo "Could not determine VT number from TTY '$TTY' (expected /dev/ttyN)" >&2
  exit 1
fi

# Unblank the TTY
setterm --term linux --blank poke < "$TTY" > "$TTY"

# Start the uv-managed clock dashboard on this VT and switch to it
openvt -f -c "$VT_NUM" -s -- bash -lc 'cd /home/bol/clock && TERM=linux uv run clock'
