#!/usr/bin/env bash
set -euo pipefail

# Dedicated demo host only. Docker must use its iptables backend.
chain=PLDEMO-IMDS
iptables -w -nL DOCKER-USER >/dev/null
iptables -w -N "$chain" 2>/dev/null || iptables -w -nL "$chain" >/dev/null
# Install the fail-closed rule first, then the single task-network exception.
if ! iptables -w -C "$chain" -j DROP 2>/dev/null; then
    iptables -w -A "$chain" -j DROP
fi
if ! iptables -w -C "$chain" -i pldemo-egress -s 172.29.79.2/32 -j RETURN 2>/dev/null; then
    iptables -w -I "$chain" 1 -i pldemo-egress -s 172.29.79.2/32 -j RETURN
fi
if ! iptables -w -C DOCKER-USER -d 169.254.169.254/32 -j "$chain" 2>/dev/null; then
    iptables -w -I DOCKER-USER 1 -d 169.254.169.254/32 -j "$chain"
fi
