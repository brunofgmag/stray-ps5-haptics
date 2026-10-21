#!/usr/bin/env bash
exec python3 -I "$(dirname "$(readlink -f "$0")")/install.py" "$@"
