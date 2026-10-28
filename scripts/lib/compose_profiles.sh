#!/bin/bash
# scripts/lib/compose_profiles.sh
#
# One reader for COMPOSE_PROFILES and for the profiles a compose file declares,
# shared by scripts/deploy.sh, scripts/ci/check-required-secrets.sh and
# scripts/ci/post-deploy-verify.sh (docs/deployment.md#source-workers-are-compose-profiles).
# Meant to be sourced. It uses the .env rules of scripts/lib/dotenv.sh, which
# follow docker-compose: an `export ` prefix, leading whitespace, quotes, CRLF
# and a trailing ` # comment` are all handled.

_COMPOSE_PROFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/dotenv.sh
. "$_COMPOSE_PROFILES_DIR/dotenv.sh"

# dotenv_value CONTENT KEY: print the value of the last assignment of KEY in the
# .env text CONTENT. Exit 1 when there is none or its value is empty.
dotenv_value() {
    local content="$1" key="$2" line assignment value="" found=1
    while IFS= read -r line || [[ -n "$line" ]]; do
        assignment="$(dotenv_parse_line "$line")"
        if [[ "${assignment%%=*}" == "$key" && -n "$assignment" ]]; then
            value="${assignment#*=}"
            # `KEY= # note`: nothing precedes the comment, so the value is empty.
            if [[ "$value" == \#* ]]; then value=""; fi
            found=0
        fi
    done <<< "$content"
    if [[ "$found" -ne 0 || -z "$value" ]]; then
        return 1
    fi
    printf '%s' "$value"
}

# compose_profiles_value CONTENT: the COMPOSE_PROFILES list of the .env text
# CONTENT, spaces removed. Exit 1 when it is missing or empty.
compose_profiles_value() {
    local value
    value="$(dotenv_value "$1" COMPOSE_PROFILES)" || return 1
    value="${value//[[:space:]]/}"
    [[ -n "$value" ]] || return 1
    printf '%s' "$value"
}

# compose_service_profiles COMPOSE_TEXT: print `service profile` for every
# profile of every service. The compose files write them one per line in flow
# style: `profiles: ["youtube"]`.
compose_service_profiles() {
    printf '%s\n' "$1" | awk '
        /^[^ #]/ { in_services = ($0 ~ /^services:/) }
        in_services && /^  [A-Za-z0-9_.-]+:[[:space:]]*$/ { svc = $1; sub(/:$/, "", svc) }
        in_services && svc != "" && /^ +profiles: *\[/ {
            line = $0
            sub(/^[^[]*\[/, "", line); sub(/\].*$/, "", line)
            n = split(line, parts, ",")
            for (i = 1; i <= n; i++) {
                p = parts[i]; gsub(/[ "\047]/, "", p)
                if (p != "") print svc, p
            }
        }'
}

# compose_disabled_services COMPOSE_TEXT ENABLED: print the services (space
# separated) that sit behind profiles and none of them is in the comma separated
# list ENABLED.
compose_disabled_services() {
    local svc profile out="" enabled=",$2," seen=" "
    declare -A on=()
    while read -r svc profile; do
        [[ -n "$svc" ]] || continue
        if [[ "$enabled" == *",$profile,"* ]]; then on[$svc]=1; fi
        if [[ "$seen" != *" $svc "* ]]; then seen+="$svc "; fi
    done < <(compose_service_profiles "$1")
    for svc in $seen; do
        [[ -n "${on[$svc]:-}" ]] || out+="$svc "
    done
    printf '%s' "${out% }"
}
