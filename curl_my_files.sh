#!/usr/bin/env bash
set -euo pipefail

# vars
KEYCHAIN_ENTRY="Passphrase"
ENCRYPTED_TOKEN_URL="https://raw.githubusercontent.com/username/dotfiles/main/secrets/github_token.gpg"
PRIVATE_REPO="https://raw.githubusercontent.com/username/private-repo/main"
TMP_GPG="/tmp/token.gpg"
TMP_TOKEN="/tmp/token"

# funcs
fail() {
    echo "ERROR: $1" >&2
    exit 1
}

secure_rm() {
    shred -vfz -n 3 "$@" 2>/dev/null || rm -f "$@" || true
}

# check gpg is installed
command -v gpg >/dev/null 2>&1 || fail "gpg not installed"

# check curl is installed
command -v curl >/dev/null 2>&1 || fail "curl not installed"

# check keychain entry exists
if ! security find-generic-password -s "$KEYCHAIN_ENTRY" >/dev/null 2>&1; then
    fail "Keychain entry \"$KEYCHAIN_ENTRY\" not found"
fi

# get passphrase from keychain
PASSPHRASE="$(security find-generic-password -s "$KEYCHAIN_ENTRY" -w)"
if [[ -z "$PASSPHRASE" ]]; then
    fail "Keychain returned an empty passphrase"
fi

# grab encrypted token
curl -fsSL "$ENCRYPTED_TOKEN_URL" -o "$TMP_GPG" \
    || fail "Failed to download encrypted token"

# decrypt using passphrase
gpg --quiet --batch --yes \
    --pinentry-mode loopback \
    --no-symkey-cache \
    --decrypt \
    --passphrase="$PASSPHRASE" \
    --output "$TMP_TOKEN" \
    "$TMP_GPG" \
    || fail "GPG decryption failed"

# read token
TOKEN="$(cat "$TMP_TOKEN")"
if [[ -z "$TOKEN" ]]; then
    fail "Decrypted token file is empty"
fi

# use token to access private repo
curl -fsSL \
    -H "Authorization: token $TOKEN" \
    "$PRIVATE_REPO/file.txt" \
    -o output.txt \
    || fail "Failed to download private file"

# security cleanup
secure_rm "$TMP_GPG" "$TMP_TOKEN"
unset PASSPHRASE TOKEN

# finished
echo "Success!"