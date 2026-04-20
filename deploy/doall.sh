#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="2.1.86"
API_KEY="openclaude-0PbTd-meaBPKINR_b6G4HgQqH16ddp-F3nQaPq1HSkByunyj"
BASE_URL="https://open-claude.com/v1"
WRITE_SHELL=1
PROMPT_API=0

# Standard Modell-Definitionen
MODEL_OPUS="claude-opus-4.6"
MODEL_SONNET="claude-sonnet-4.6"
MODEL_HAIKU="claude-haiku-4.5"

SETTINGS_DIR="${HOME}/.claude"
SETTINGS_PATH="${SETTINGS_DIR}/settings.json"

usage() {
  cat <<'USAGE'
Usage:
  ./doall.sh [--version 2.1.86] [--api-key <key>] [--base-url <url>] [--configure-api] [--no-shell]

Was das Skript macht (Optimiert für macOS):
  1) Installiert Claude Code (npm)
  2) Konfiguriert API Key & Base URL
  3) Aktualisiert ~/.claude/settings.json
  4) Schreibt Umgebungsvariablen in ~/.zshrc (Standard auf Mac) und andere Profile
USAGE
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

err() {
  printf '[ERR] %s\n' "$*" >&2
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "Fehlender Befehl: ${cmd}. Bitte installiere diesen (z.B. via Homebrew)."
    exit 1
  fi
}

trim_spaces() {
  local s="$1"
  s="${s#${s%%[![:space:]]*}}"
  s="${s%${s##*[![:space:]]}}"
  printf '%s' "$s"
}

normalize_base_url() {
  local u
  u="$(trim_spaces "$1")"
  u="${u%/}"
  printf '%s' "$u"
}

is_tty() {
  [[ -t 0 && -t 1 ]]
}

read_env_from_settings() {
  local key="$1"
  python3 - "$SETTINGS_PATH" "$key" <<'PY'
import json
import os
import sys

path = sys.argv[1]
key = sys.argv[2]

if not os.path.exists(path):
    raise SystemExit(0)

try:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
except Exception:
    raise SystemExit(0)

env = data.get('env') or {}
value = env.get(key)
if isinstance(value, str):
    print(value)
PY
}

write_settings_json() {
  python3 - "$SETTINGS_PATH" "$API_KEY" "$BASE_URL" "$MODEL_OPUS" "$MODEL_SONNET" "$MODEL_HAIKU" <<'PY'
import json
import os
import sys

path, api_key, base_url, opus, sonnet, haiku = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]

if os.path.exists(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}
else:
    data = {}

env = data.get('env') or {}
env['ANTHROPIC_API_KEY'] = api_key
env['ANTHROPIC_BASE_URL'] = base_url
env['ANTHROPIC_DEFAULT_OPUS_MODEL'] = env.get('ANTHROPIC_DEFAULT_OPUS_MODEL') or opus
env['ANTHROPIC_DEFAULT_SONNET_MODEL'] = env.get('ANTHROPIC_DEFAULT_SONNET_MODEL') or sonnet
env['ANTHROPIC_DEFAULT_HAIKU_MODEL'] = env.get('ANTHROPIC_DEFAULT_HAIKU_MODEL') or haiku
env['API_TIMEOUT_MS'] = str(env.get('API_TIMEOUT_MS') or '3000000')
data['env'] = env

permissions = data.get('permissions')
if not isinstance(permissions, dict):
    permissions = {'allow': ['*']}
data['permissions'] = permissions

os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY
}

upsert_shell_block() {
  local file="$1"
  [ ! -f "$file" ] && touch "$file"
  
  # macOS/BSD sed Fix: Benötigt '' nach -i
  sed -i '' '/# >>> claude-api-config >>>/,/# <<< claude-api-config <<</d' "$file" || true
  
  cat >> "$file" <<SHELL_BLOCK

# >>> claude-api-config >>>
export ANTHROPIC_API_KEY='${API_KEY}'
export ANTHROPIC_BASE_URL='${BASE_URL}'
unset ANTHROPIC_AUTH_TOKEN
unset ANTHROPIC_MODEL
export ANTHROPIC_DEFAULT_OPUS_MODEL='${MODEL_OPUS}'
export ANTHROPIC_DEFAULT_SONNET_MODEL='${MODEL_SONNET}'
export ANTHROPIC_DEFAULT_HAIKU_MODEL='${MODEL_HAIKU}'
export API_TIMEOUT_MS='3000000'
# <<< claude-api-config <<<
SHELL_BLOCK
}

# --- Rest der Logik bleibt ähnlich, aber optimiert ---

require_cmd npm
require_cmd python3

# Argument Parsing (wie im Original...)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) TARGET_VERSION="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --configure-api) PROMPT_API=1; shift ;;
    --no-shell) WRITE_SHELL=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "Unbekannt: $1"; usage; exit 1 ;;
  esac
done

if [[ "$PROMPT_API" -eq 1 ]]; then
  read -r -s -p "Enter API key: " API_KEY; echo
  read -r -p "Enter base URL: " BASE_URL
fi

# Fallbacks & Normalisierung
API_KEY="${API_KEY:-${ANTHROPIC_API_KEY:-$(read_env_from_settings 'ANTHROPIC_API_KEY' || true)}}"
BASE_URL="${BASE_URL:-${ANTHROPIC_BASE_URL:-$(read_env_from_settings 'ANTHROPIC_BASE_URL' || true)}}"

if [[ -z "$API_KEY" || -z "$BASE_URL" ]]; then
  err "API Key oder Base URL fehlt!"
  exit 1
fi

BASE_URL="$(normalize_base_url "$BASE_URL")"

# Installation
log "Installiere Claude Code ${TARGET_VERSION}..."
sudo npm install -g "@anthropic-ai/claude-code@${TARGET_VERSION}"

# Konfiguration schreiben
log "Schreibe Einstellungen..."
write_settings_json

if [[ "$WRITE_SHELL" -eq 1 ]]; then
  log "Aktualisiere Shell-Profile..."
  # Auf dem Mac ist .zshrc das wichtigste File
  [[ -f "${HOME}/.zshrc" ]] && upsert_shell_block "${HOME}/.zshrc"
  [[ -f "${HOME}/.bash_profile" ]] && upsert_shell_block "${HOME}/.bash_profile"
  [[ -f "${HOME}/.profile" ]] && upsert_shell_block "${HOME}/.profile"
fi

log "Fertig! Bitte starte dein Terminal neu oder nutze: source ~/.zshrc"
