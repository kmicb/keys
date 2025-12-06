#!/usr/bin/env bash
set -euo pipefail

# disable core dumps to prevent creds from being potentially stored
ulimit -c 0

# vars
KEYCHAIN_ENTRY="Passphrase"
ENCRYPTED_TOKEN_URL="https://github.com/kmicb/keys/raw/refs/heads/main/gh_token.txt.gpg"
PRIVATE_REPO="https://github.com/kmicb/rpi/raw/refs/heads/main"
TMP_GPG=$(mktemp) && chmod 600 "$TMP_GPG"
TMP_TOKEN=$(mktemp) && chmod 600 "$TMP_TOKEN"

# funcs
fail() {
    echo "ERROR: $1" >&2
    exit 1
}

secure_rm() {
    shred -vfz -n 3 "$@" 2>/dev/null || rm -f "$@" || true
}

download_file() {
    local url="$1"
    local out="$2"
    curl -fsSL -H "Authorization: token $TOKEN" "$url" -o "$out" || fail "Failed to download $out"
}

trap 'secure_rm "$TMP_GPG" "$TMP_TOKEN" 2>/dev/null; unset TOKEN' EXIT

# check commands
command -v gpg >/dev/null 2>&1 || fail "gpg not installed"
command -v curl >/dev/null 2>&1 || fail "curl not installed"
command -v security >/dev/null 2>&1 || fail "security command not found (you're not on macOS)"

# check keychain entry exists
if ! security find-generic-password -s "$KEYCHAIN_ENTRY" >/dev/null 2>&1; then
    fail "Keychain entry \"$KEYCHAIN_ENTRY\" not found."
fi

# grab encrypted token
curl -fsSL "$ENCRYPTED_TOKEN_URL" -o "$TMP_GPG" || fail "Failed to download encrypted token"

# decrypt using passphrase
security find-generic-password -s "$KEYCHAIN_ENTRY" -w | \
    gpg --quiet --batch --yes \
        --pinentry-mode loopback \
        --no-symkey-cache \
        --decrypt \
        --passphrase-fd 0 \
        --output "$TMP_TOKEN" \
        "$TMP_GPG" 2>/dev/null || fail "GPG decryption failed"

# read token
read -r TOKEN < "$TMP_TOKEN"
[[ -n "$TOKEN" ]] || fail "Decrypted token file is empty"

download_file "$PRIVATE_REPO/setup_rpi.py" "setup_rpi.py"
download_file "$PRIVATE_REPO/config.ini" "config.ini"

# finished
echo "Success!"