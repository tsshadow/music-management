#!/usr/bin/env bash
# Install muma-ro, the read-only command wrapper, on one host (issue #176,
# docs/designs/claude-readonly-access/technical.md).
#
# A person runs this, as root, on the host it names. An agent never does: an agent never installs
# its own access. Without --apply it prints every change and does nothing. With --apply it prints
# them again and applies them only after the person types "yes". It ends with the self-test; a
# failed self-test removes the install again.
#
#   scripts/muma-ro/install.sh --class prod --key-name workstation \
#       --pubkey muma-ro-prod_ed25519.pub --client 192.0.2.10 [--policy policy.json] [--apply]
#   scripts/muma-ro/install.sh --uninstall [--apply]
#
# --class     prod, devvm, runner, nas or proxmox: picks tools/muma_ro/policies/<class>.example.json
# --policy    the host's own policy instead of the example; an existing /etc/muma-ro/policy.json
#             is kept unless --policy is given
# --key-name  the name the audit log shows for this key (letters, digits, _ . -)
# --pubkey    the client's public key file, one ssh-ed25519 line
# --client    the address the key may connect from
set -euo pipefail

ACCOUNT=muma-ro
HOME_DIR=/var/lib/muma-ro
LIB_DIR=/usr/local/lib/muma-ro
ZIPAPP=$LIB_DIR/muma-ro.pyz
LAUNCHER=/usr/local/bin/muma-ro
HELPER=/usr/local/libexec/muma-ro-priv
POLICY_DIR=/etc/muma-ro
POLICY=$POLICY_DIR/policy.json
SUDOERS=/etc/sudoers.d/muma-ro
KEYS=$HOME_DIR/.ssh/authorized_keys
PYTHON=/usr/bin/python3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() {
    sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
}

die() {
    echo "install.sh: $*" >&2
    exit 1
}

APPLY=0
STEPS=0

# step <description> <command> [args...]: print it, or run it.
step() {
    local description=$1
    shift
    STEPS=$((STEPS + 1))
    if [ "$APPLY" = 1 ]; then
        echo "--- $description"
        "$@"
    else
        printf '  %2d. %s\n      %s\n' "$STEPS" "$description" "$*"
    fi
}

# write_file <path> <mode> <content>: create or replace one root-owned file.
write_file() {
    local path=$1 mode=$2 content=$3
    if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
        return 0
    fi
    STEPS=$((STEPS + 1))
    if [ "$APPLY" = 1 ]; then
        echo "--- write $path"
        install -m "$mode" -o root -g root /dev/null "$path"
        printf '%s\n' "$content" >"$path"
    else
        printf '  %2d. write %s (mode %s, root):\n' "$STEPS" "$path" "$mode"
        printf '%s\n' "$content" | sed 's/^/        | /'
    fi
}

# build_zipapp <output>: the package, the masking module it shares with the MCP server, and an
# entry point. Standard library only, so the host needs nothing but python3.
build_zipapp() {
    local out=$1 stage
    stage=$(mktemp -d)
    mkdir -p "$stage/tools/muma_ro" "$stage/tools/muma_mcp"
    : >"$stage/tools/__init__.py"
    cp "$REPO_ROOT"/tools/muma_ro/*.py "$stage/tools/muma_ro/"
    cp "$REPO_ROOT/tools/muma_mcp/__init__.py" "$REPO_ROOT/tools/muma_mcp/redact.py" "$stage/tools/muma_mcp/"
    printf 'import sys\nfrom tools.muma_ro.__main__ import entry\nsys.exit(entry())\n' >"$stage/__main__.py"
    "$PYTHON" -m zipapp "$stage" -o "$out"
    rm -rf "$stage"
}

install_zipapp() {
    local tmp
    tmp=$(mktemp)
    build_zipapp "$tmp"
    install -d -m 0755 -o root -g root "$LIB_DIR"
    install -m 0644 -o root -g root "$tmp" "$ZIPAPP"
    rm -f "$tmp"
}

install_sudoers() {
    local tmp
    tmp=$(mktemp)
    printf '%s ALL=(root) NOPASSWD: %s\n' "$ACCOUNT" "$HELPER" >"$tmp"
    visudo -cf "$tmp" >/dev/null || {
        rm -f "$tmp"
        die "visudo refuses the sudoers line; nothing written to $SUDOERS"
    }
    install -m 0440 -o root -g root "$tmp" "$SUDOERS"
    rm -f "$tmp"
}

create_account() {
    useradd --system --home-dir "$HOME_DIR" --create-home --shell /bin/sh "$ACCOUNT"
    passwd -l "$ACCOUNT" >/dev/null
}

check_not_in_docker_group() {
    if id -nG "$ACCOUNT" | tr ' ' '\n' | grep -qx docker; then
        die "$ACCOUNT is in the docker group, which is root on this host; remove it first"
    fi
}

# The account must not change its own keys, so .ssh and the key file belong to root.
install_key_dir() {
    install -d -m 0755 -o root -g root "$HOME_DIR/.ssh"
}

remove_everything() {
    rm -f "$KEYS" "$SUDOERS" "$LAUNCHER" "$HELPER" "$ZIPAPP"
    rmdir "$LIB_DIR" 2>/dev/null || true
    rm -rf "$POLICY_DIR"
    if id "$ACCOUNT" >/dev/null 2>&1; then
        userdel --remove "$ACCOUNT" 2>/dev/null || userdel "$ACCOUNT"
    fi
}

self_test() {
    if ! sudo -u "$ACCOUNT" -H "$LAUNCHER" --key self-test --self-test; then
        echo "install.sh: the self-test failed; removing the install again" >&2
        remove_everything
        exit 1
    fi
}

# --- the plan ---

plan_install() {
    [ -n "${CLASS:-}" ] || die "--class is required"
    [ -n "${KEY_NAME:-}" ] || die "--key-name is required"
    [ -n "${PUBKEY:-}" ] || die "--pubkey is required"
    [ -n "${CLIENT:-}" ] || die "--client is required"
    case "$CLASS" in prod | devvm | runner | nas | proxmox) ;; *) die "--class must be prod, devvm, runner, nas or proxmox" ;; esac
    case "$KEY_NAME" in '' | *[!A-Za-z0-9_.-]*) die "--key-name is letters, digits, _ . and -" ;; esac
    case "$CLIENT" in *[!A-Za-z0-9.:/-]*) die "--client must be one address or network" ;; esac
    [ -f "$PUBKEY" ] || die "$PUBKEY does not exist"
    [ "$(wc -l <"$PUBKEY")" -le 1 ] || die "$PUBKEY must hold one key"
    local key
    key=$(cat "$PUBKEY")
    case "$key" in ssh-ed25519\ *) ;; *) die "$PUBKEY is not an ssh-ed25519 public key" ;; esac
    case "$key" in *\"* | *,*) die "$PUBKEY has characters an authorized_keys line cannot hold" ;; esac

    [ -x "$PYTHON" ] || die "$PYTHON is missing; muma-ro needs Python 3.9 or later"
    "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 9))' || die "muma-ro needs Python 3.9 or later"
    command -v visudo >/dev/null 2>&1 || die "visudo is missing; install sudo first"
    command -v sshd >/dev/null 2>&1 || [ -x /usr/sbin/sshd ] || die "sshd is missing"

    local policy_source=${POLICY_FILE:-$REPO_ROOT/tools/muma_ro/policies/$CLASS.example.json}
    [ -f "$policy_source" ] || die "$policy_source does not exist"
    PYTHONPATH="$REPO_ROOT" "$PYTHON" -I -c '
import json, sys
sys.path.insert(0, sys.argv[2])
from tools.muma_ro.policy import from_dict
policy = from_dict(json.load(open(sys.argv[1])))
if policy.host_class != sys.argv[3]:
    sys.exit(f"the policy is for class {policy.host_class}, not {sys.argv[3]}")
' "$policy_source" "$REPO_ROOT" "$CLASS" || die "$policy_source is not a valid policy"

    if ! id "$ACCOUNT" >/dev/null 2>&1; then
        step "create the account $ACCOUNT (shell /bin/sh, password locked, no groups)" create_account
    fi
    step "check that $ACCOUNT is not in the docker group" check_not_in_docker_group
    step "build the zipapp from tools/muma_ro and install it as $ZIPAPP" install_zipapp
    write_file "$LAUNCHER" 0755 "#!/bin/sh
exec $PYTHON -I $ZIPAPP \"\$@\""
    step "create $(dirname "$HELPER")" install -d -m 0755 -o root -g root "$(dirname "$HELPER")"
    write_file "$HELPER" 0755 "#!/bin/sh
exec $PYTHON -I $ZIPAPP --priv \"\$@\""
    step "create $POLICY_DIR" install -d -m 0755 -o root -g root "$POLICY_DIR"
    if [ -n "${POLICY_FILE:-}" ] || [ ! -f "$POLICY" ]; then
        write_file "$POLICY" 0644 "$(cat "$policy_source")"
    else
        echo "  (keeping the existing $POLICY; pass --policy to replace it)"
    fi
    step "write $SUDOERS after visudo -c accepts it" install_sudoers
    step "create $HOME_DIR/.ssh, owned by root" install_key_dir
    write_file "$KEYS" 0644 "restrict,from=\"$CLIENT\",command=\"$LAUNCHER --key $KEY_NAME\" $key"
    step "run the self-test as $ACCOUNT; a failure removes the install" self_test
}

plan_uninstall() {
    step "remove the key, sudoers, launchers, zipapp, policy and the account $ACCOUNT" remove_everything
}

# --- main ---

UNINSTALL=0
while [ $# -gt 0 ]; do
    case "$1" in
        --class) CLASS=${2:-} && shift ;;
        --key-name) KEY_NAME=${2:-} && shift ;;
        --pubkey) PUBKEY=${2:-} && shift ;;
        --client) CLIENT=${2:-} && shift ;;
        --policy) POLICY_FILE=${2:-} && shift ;;
        --apply) WANT_APPLY=1 ;;
        --uninstall) UNINSTALL=1 ;;
        -h | --help) usage ;;
        *) usage ;;
    esac
    shift
done

if [ "${WANT_APPLY:-0}" = 1 ] && [ "$(id -u)" != 0 ]; then
    die "run it as root"
fi

echo "muma-ro on $(hostname): the changes"
if [ "$UNINSTALL" = 1 ]; then plan_uninstall; else plan_install; fi

if [ "${WANT_APPLY:-0}" != 1 ]; then
    echo "Dry run: nothing changed. Run it again with --apply to apply these $STEPS changes."
    exit 0
fi

read -r -p "Type yes to apply these $STEPS changes: " answer
[ "$answer" = yes ] || die "nothing changed"

STEPS=0
APPLY=1
if [ "$UNINSTALL" = 1 ]; then plan_uninstall; else plan_install; fi
echo "Done. The agent's command log: journalctl -t muma-ro"
