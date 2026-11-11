#!/usr/bin/env bash
set -euo pipefail

deadline_file=${1:-/etc/premier-league-demo/deadline}
# Fail closed if the approved deadline was lost or corrupted.
deadline=$(cat "$deadline_file" 2>/dev/null || true)
now=$(date -u +%s)
if [[ ! $deadline =~ ^[1-9][0-9]{9}$ ]] || (( now >= deadline )); then
    systemctl --no-block poweroff
fi
