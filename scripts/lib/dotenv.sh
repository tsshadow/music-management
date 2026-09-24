#!/bin/bash
# scripts/lib/dotenv.sh
#
# A .env reader for the deploy scripts. Meant to be sourced.
#
# It replaces a `sed 's/[[:space:]]*#.*$//'` one-liner in scripts/deploy.sh that
# treated every `#` as the start of a comment, so `MYSQL_ROOT_PASSWORD=ab#cd`
# arrived as `ab` and every migration failed to log in -- while docker-compose,
# reading the same file for the stack itself, saw the whole password. See
# docs/bug-reports/038-deploy-puts-every-prod-secret-on-the-command-line.md.
#
# The rules follow what docker-compose (python-dotenv) does with the same file,
# because a line that means one thing to compose and another to the migration
# step is exactly the bug above:
#   - blank lines and lines whose first non-blank character is `#` are skipped;
#   - an optional leading `export ` is ignored;
#   - the key is everything before the first `=`, and must be a valid name;
#   - a value in single or double quotes is taken literally up to the closing
#     quote, `#` included;
#   - an unquoted value ends at the first whitespace-then-`#` (an inline
#     comment); a `#` with no whitespace before it is part of the value;
#   - surrounding whitespace around an unquoted value is trimmed.

# dotenv_ltrim VALUE: print VALUE without leading whitespace.
dotenv_ltrim() {
    local value="$1"
    printf '%s' "${value#"${value%%[![:space:]]*}"}"
}

# dotenv_rtrim VALUE: print VALUE without trailing whitespace.
dotenv_rtrim() {
    local value="$1"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}

# dotenv_parse_line LINE: print `KEY=VALUE` for an assignment line, and nothing
# for a blank line, a comment or a line that is not an assignment.
dotenv_parse_line() {
    local line="$1" key value rest
    line="${line%$'\r'}"
    line="$(dotenv_ltrim "$line")"
    if [[ -z "$line" || "$line" == \#* ]]; then
        return 0
    fi
    if [[ "$line" =~ ^export[[:space:]]+ ]]; then
        line="${line#"${BASH_REMATCH[0]}"}"
    fi
    if [[ "$line" != *=* ]]; then
        return 0
    fi
    key="$(dotenv_rtrim "${line%%=*}")"
    if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        return 0
    fi
    value="$(dotenv_ltrim "${line#*=}")"
    if [[ "$value" == \'* ]]; then
        rest="${value:1}"
        value="${rest%%\'*}"
    elif [[ "$value" == \"* ]]; then
        rest="${value:1}"
        value="${rest%%\"*}"
    else
        # Leftmost whitespace-then-# starts the comment; cutting at the first
        # occurrence of that exact text is cutting at that position.
        if [[ "$value" =~ [[:space:]]# ]]; then
            value="${value%%"${BASH_REMATCH[0]}"*}"
        fi
        value="$(dotenv_rtrim "$value")"
    fi
    printf '%s=%s\n' "$key" "$value"
}

# dotenv_load FILE [--keep-existing]: export every assignment in FILE into the
# current shell. With --keep-existing a variable that is already set and
# non-empty keeps its value, so the caller's environment overrides the file.
dotenv_load() {
    local file="$1" mode="${2:-}" line assignment name
    while IFS= read -r line || [[ -n "$line" ]]; do
        assignment="$(dotenv_parse_line "$line")"
        if [[ -z "$assignment" ]]; then
            continue
        fi
        name="${assignment%%=*}"
        if [[ "$mode" == "--keep-existing" && -n "${!name:-}" ]]; then
            continue
        fi
        export "${assignment?}"
    done < "$file"
}
