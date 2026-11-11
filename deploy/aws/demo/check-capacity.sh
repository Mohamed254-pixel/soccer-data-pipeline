#!/usr/bin/env bash
set -euo pipefail

# Run on the dedicated Linux demo host or equivalent disposable VM.
# Usage: check-capacity.sh before-build|after-build|running
phase=${1:?Choose before-build, after-build or running}
root=$(docker info --format '{{.DockerRootDir}}')
available_mb=$(df -Pm "$root" | awk 'NR == 2 {print $4}')
case "$phase" in
    before-build) minimum_mb=12288 ;;
    after-build|running) minimum_mb=4096 ;;
    *) exit 2 ;;
esac
mem_total_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
mem_available_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
printf 'Docker disk free: %s MiB; host RAM total: %s KiB; host RAM available: %s KiB\n' \
    "$available_mb" "$mem_total_kb" "$mem_available_kb"
(( available_mb >= minimum_mb && mem_total_kb >= 3670016 ))
if [[ $phase == running ]]; then
    (( mem_available_kb >= 393216 ))
    mapfile -t ids < <(docker ps -q --filter label=com.docker.compose.project=premier-league-aws-demo)
    (( ${#ids[@]} == 5 ))
    docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' "${ids[@]}"
    for id in "${ids[@]}"; do
        docker exec "$id" cat /sys/fs/cgroup/memory.events |
            awk '$1 == "oom_kill" {found=1; if ($2 != 0) failed=1} END {exit (!found || failed)}'
    done
    docker inspect --format '{{.Name}} health={{.State.Health.Status}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' "${ids[@]}" |
        awk '$2 != "health=healthy" || $3 != "oom=false" || $4 != "restarts=0" {failed=1} {print} END {exit failed}'
fi
