#!/usr/bin/env bash
# Unified menu bootstrap. Does not alter nodes on startup.
set -Eeuo pipefail
umask 077
if [[ "$EUID" -ne 0 ]]; then
    echo '请使用 root 运行 / Run as root.' >&2
    exit 1
fi
BASE=https://raw.githubusercontent.com/JLX2332326532/personal-note/main/vps-sing-box-subscriptions
DIR=/root/.sbp-manager
CORE="$DIR/sbp-manager.py"
if ! command -v python3 >/dev/null || ! command -v curl >/dev/null; then
    apt-get -o DPkg::Lock::Timeout=300 update
    apt-get -o DPkg::Lock::Timeout=300 install -y python3 curl ca-certificates
fi
install -d -m 700 "$DIR"
if [[ ! -s "$CORE" ]]; then
    TMP=$(mktemp "$DIR/.manager.XXXXXX")
    trap 'rm -f "$TMP"' EXIT
    curl -fLsS --retry 2 --connect-timeout 15 "$BASE/sbp-manager.py" -o "$TMP"
    python3 - "$TMP" <<'PY'
from pathlib import Path
import sys
compile(Path(sys.argv[1]).read_text(), "sbp-manager.py", "exec")
PY
    python3 "$TMP" --self-test
    chmod 700 "$TMP"
    mv -f "$TMP" "$CORE"
    trap - EXIT
fi
export SBP_MANAGER_ENTRY="$(readlink -f "$0")"
exec python3 "$CORE" "$@"
