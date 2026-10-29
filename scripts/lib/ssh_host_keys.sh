#!/bin/bash
# scripts/lib/ssh_host_keys.sh
#
# Host key checking for the scripts that SSH into production. Meant to be sourced.
#
# Every one of them used to pass `-o StrictHostKeyChecking=no`, and the CI setup
# appended whatever `ssh-keyscan` returned to the shared runner's known_hosts
# first. Together that accepted any key at all: anything answering on the
# production address -- a reinstalled host, or something impersonating it --
# received the root key's signature, every production secret on stdin, and the
# database migrations. See docs/bug-reports/081-compose-logs-grow-without-bound.md.
#
# The production host's keys are pinned in a known_hosts file: the file-type CI/CD variable
# PROD_SSH_KNOWN_HOSTS in a pipeline, scripts/ssh/known_hosts (linked from the private muma-ops
# repository) on a workstation. A host listed there is checked against that file only, with StrictHostKeyChecking=yes: a key
# that differs fails the connection instead of being learned. A host that is not
# listed (a Portainer host, a developer's own target) falls back to accept-new
# against the user's own known_hosts, which learns a key once and refuses it if it
# changes later -- still never "accept anything".
#
# SSH_PINNED_KNOWN_HOSTS overrides both, e.g. for a one-off run after the host was reinstalled.
# Outside a pipeline, without any of the three files every host falls back to accept-new.

SSH_PINNED_KNOWN_HOSTS="${SSH_PINNED_KNOWN_HOSTS:-${PROD_SSH_KNOWN_HOSTS:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ssh/known_hosts}}"
export SSH_PINNED_KNOWN_HOSTS

# ssh_pinned_host_missing HOST: succeed (return 0) when HOST is the production
# host (PROD_REMOTE_HOST) but the pinned file (the repository's, or the one
# PROD_SSH_KNOWN_HOSTS names) has no entry for it, and
# PROD_SSH_ACCEPT_NEW_HOST_KEY=true was not set on purpose. Learning the key of
# the production host on first sight is what the pinning exists to prevent, and a
# changed PROD_REMOTE_HOST string (name instead of address) would otherwise drop
# to accept-new without a word. Prints the reason on stderr.
ssh_pinned_host_missing() {
    local host="$1"
    [ -n "${PROD_REMOTE_HOST:-}" ] && [ "$host" = "$PROD_REMOTE_HOST" ] || return 1
    [ "${PROD_SSH_ACCEPT_NEW_HOST_KEY:-}" = "true" ] && return 1
    if [ -f "$SSH_PINNED_KNOWN_HOSTS" ] \
        && ssh-keygen -F "$host" -f "$SSH_PINNED_KNOWN_HOSTS" >/dev/null 2>&1; then
        return 1
    fi
    {
        echo "Error: no pinned SSH host key for PROD_REMOTE_HOST ($host)."
        echo "  Set the file-type CI/CD variable PROD_SSH_KNOWN_HOSTS with the host's keys, or use the host"
        echo "  string that $SSH_PINNED_KNOWN_HOSTS lists. To learn the key on first use anyway,"
        echo "  set PROD_SSH_ACCEPT_NEW_HOST_KEY=true on purpose."
    } >&2
    return 0
}
export -f ssh_pinned_host_missing

# ssh_host_key_opts HOST: print the ssh -o options for HOST, one argument per
# line (read them with `mapfile -t`, so a path with spaces stays one argument).
#
# In a pipeline (CI is set) a host that the pinned file does not list is an error: the
# function prints why on stderr and returns 1, because accept-new would learn whatever key
# answers. PROD_SSH_ACCEPT_NEW_HOST_KEY=true is the one explicit opt-in. Outside a pipeline
# an unlisted host falls back to accept-new.
ssh_host_key_opts() {
    local host="$1"
    if [ -s "$SSH_PINNED_KNOWN_HOSTS" ] \
        && ssh-keygen -F "$host" -f "$SSH_PINNED_KNOWN_HOSTS" 2>/dev/null | grep -q .; then
        printf '%s\n' -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$SSH_PINNED_KNOWN_HOSTS"
    elif ssh_pinned_host_missing "$host"; then
        # The production host (PROD_REMOTE_HOST) is never learned on first sight, in a
        # pipeline or on a workstation, unless PROD_SSH_ACCEPT_NEW_HOST_KEY=true says so.
        return 1
    elif [ -n "${CI:-}" ] && [ "${PROD_SSH_ACCEPT_NEW_HOST_KEY:-}" != "true" ]; then
        echo "Error: no pinned host key for $host in '$SSH_PINNED_KNOWN_HOSTS'." >&2
        echo "  Set the file-type CI/CD variable PROD_SSH_KNOWN_HOSTS to the host's public keys," >&2
        echo "  or set PROD_SSH_ACCEPT_NEW_HOST_KEY=true to learn the key on first use." >&2
        return 1
    else
        printf '%s\n' -o StrictHostKeyChecking=accept-new
    fi
}
export -f ssh_host_key_opts

# ssh_host_key_opts_into ARRAY HOST: fill the array named ARRAY with the options for HOST.
# Unlike `mapfile -t A < <(ssh_host_key_opts ...)` it passes the failure on, so callers
# can stop: `ssh_host_key_opts_into OPTS "$host" || exit 1`.
ssh_host_key_opts_into() {
    local -n _into="$1"
    local out
    out="$(ssh_host_key_opts "$2")" || return 1
    mapfile -t _into <<<"$out"
}
export -f ssh_host_key_opts_into
