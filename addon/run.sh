#!/usr/bin/env bash
set -euo pipefail

echo "=== Clanker Add-on Starting ==="

# HA Supervisor provides these automatically
HA_TOKEN="${SUPERVISOR_TOKEN:-}"
HA_URL="http://supervisor/core"

# Read add-on options
OPTIONS_FILE="/data/options.json"
if [ ! -f "$OPTIONS_FILE" ]; then
    echo "ERROR: Options file not found"
    exit 1
fi

read_opt() {
    python3 -c "import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], sys.argv[3]))" \
        "$OPTIONS_FILE" "$1" "$2"
}

INSTALL_OLLAMA=$(read_opt "Install Ollama add-on" "False")
INSTALL_VOICE=$(read_opt "Install voice add-ons (Whisper, Piper, Wake Word)" "False")
ANTHROPIC_KEY=$(read_opt anthropic_api_key "")
OPENAI_KEY=$(read_opt openai_api_key "")
OLLAMA_URL=$(read_opt ollama_url "")
OLLAMA_MODEL=$(read_opt ollama_model "llama3.2")
DEFAULT_PROVIDER=$(read_opt default_provider "ollama")
TTS_ENGINE=$(read_opt tts_engine "tts.piper")
LOG_LEVEL=$(read_opt log_level "INFO")

SUPERVISOR_API="http://supervisor"
AUTH_HEADER="Authorization: Bearer ${HA_TOKEN}"

# --- Install companion add-ons (if enabled) ---

find_addon_slug() {
    # Search the store for an add-on by name substring, return its slug
    local search="$1"
    curl -s -H "$AUTH_HEADER" "$SUPERVISOR_API/store/addons" 2>/dev/null | \
        python3 -c "
import json, sys
data = json.load(sys.stdin).get('data', {}).get('addons', [])
for a in data:
    if '${search}'.lower() in a.get('name','').lower() or '${search}'.lower() in a.get('slug','').lower():
        print(a['slug'])
        break
" 2>/dev/null || echo ""
}

install_addon() {
    local repo="$1" slug="$2" name="$3" search_name="$4"

    # If slug is empty, try to find it dynamically
    if [ -z "$slug" ] && [ -n "$search_name" ]; then
        slug=$(find_addon_slug "$search_name")
        if [ -n "$slug" ]; then
            echo "$name: found in store as $slug"
        fi
    fi

    # Add repo first if we still don't have a slug
    if [ -z "$slug" ] && [ -n "$repo" ]; then
        echo "$name: adding repository $repo..."
        curl -s -X POST -H "$AUTH_HEADER" -H "Content-Type: application/json" \
            -d "{\"repository\": \"$repo\"}" "$SUPERVISOR_API/store/repositories" 2>&1 || true
        echo "$name: waiting for store refresh..."
        sleep 15
        slug=$(find_addon_slug "$search_name")
        if [ -n "$slug" ]; then
            echo "$name: found in store as $slug"
        else
            echo "$name: ERROR - not found in store after adding repo"
            return 1
        fi
    fi

    if [ -z "$slug" ]; then
        echo "$name: ERROR - could not determine slug"
        return 1
    fi

    echo "$name: checking status (slug: $slug)..."

    # Check if already running
    local state
    state=$(curl -s -H "$AUTH_HEADER" "$SUPERVISOR_API/addons/$slug/info" 2>/dev/null | \
        python3 -c "import json,sys; print(json.load(sys.stdin).get('data',{}).get('state',''))" 2>/dev/null || echo "")

    if [ "$state" = "started" ]; then
        echo "$name: already running"
        return 0
    fi

    # Install if not running
    if [ "$state" != "stopped" ]; then
        echo "$name: installing (this may take a few minutes)..."
        local install_resp
        install_resp=$(curl -s -X POST -H "$AUTH_HEADER" "$SUPERVISOR_API/addons/$slug/install" 2>&1)
        echo "$name: install response: $install_resp"
        sleep 10
    fi

    # Start
    echo "$name: starting..."
    local start_resp
    start_resp=$(curl -s -X POST -H "$AUTH_HEADER" "$SUPERVISOR_API/addons/$slug/start" 2>&1)
    echo "$name: start response: $start_resp"
    sleep 5
    echo "$name: done"
}

if [ "$INSTALL_OLLAMA" = "True" ] || [ "$INSTALL_OLLAMA" = "true" ]; then
    echo "=== Installing Ollama Add-on ==="
    install_addon "https://github.com/SirUli/homeassistant-ollama-addon" "" "Ollama" "ollama"
fi

if [ "$INSTALL_VOICE" = "True" ] || [ "$INSTALL_VOICE" = "true" ]; then
    echo "=== Installing Voice Add-ons ==="
    install_addon "" "" "Whisper (STT)" "whisper"
    install_addon "" "" "Piper (TTS)" "piper"
    install_addon "" "" "openWakeWord" "openwakeword"
fi

# Auto-detect Ollama add-on if URL not set
if [ -z "$OLLAMA_URL" ]; then
    for url in "http://homeassistant.local:11434" "http://localhost:11434"; do
        if curl -sf -o /dev/null "$url/api/tags" 2>/dev/null; then
            OLLAMA_URL="$url"
            echo "Auto-detected Ollama at $OLLAMA_URL"
            break
        fi
    done
fi

# --- Install custom component ---
if [ -d "/app/ha_component/custom_components/clanker" ]; then
    mkdir -p /config/custom_components
    cp -r /app/ha_component/custom_components/clanker /config/custom_components/clanker
    echo "Custom component installed"
fi

# --- Add to HA config ---
if [ -f "/config/configuration.yaml" ] && ! grep -q "clanker:" /config/configuration.yaml; then
    printf '\nclanker:\n  url: "http://localhost:8472"\n' >> /config/configuration.yaml
    echo "Added clanker to HA configuration.yaml"
fi

# --- Generate config ---
mkdir -p /app/config
cat > /app/config/clanker.yaml << YAML
ha:
  url: "${HA_URL}"
ollama:
  base_url: "${OLLAMA_URL}"
  model: "${OLLAMA_MODEL}"
  max_tokens: 4096
  keep_alive: -1
  num_ctx: 1024
  num_gpu: 999
default_provider: ${DEFAULT_PROVIDER}
memory:
  db_path: "/data/clanker.db"
  markdown_dir: "/data/memory"
  chromadb_path: "/data/chroma"
conversation:
  host: "0.0.0.0"
  port: 8472
  tts_engine: "${TTS_ENGINE}"
log_level: ${LOG_LEVEL}
YAML

cat > /app/.env << ENV
CLANKER_HA__TOKEN=${HA_TOKEN}
ENV
[ -n "$ANTHROPIC_KEY" ] && echo "CLANKER_ANTHROPIC__API_KEY=${ANTHROPIC_KEY}" >> /app/.env
[ -n "$OPENAI_KEY" ] && echo "CLANKER_OPENAI__API_KEY=${OPENAI_KEY}" >> /app/.env

echo "=== Starting Clanker ==="
echo "Provider: ${DEFAULT_PROVIDER} | Ollama: ${OLLAMA_URL:-not found}"

cd /app

# Start the web UI on the Ingress port (background)
python3 -c "
from clanker.setup.web import run_server
run_server(port=8471)
" &
echo "Web UI started on port 8471 (Ingress)"

# Start Clanker main process
exec python3 -m clanker.main
