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

ANTHROPIC_KEY=$(read_opt anthropic_api_key "")
OPENAI_KEY=$(read_opt openai_api_key "")
OLLAMA_URL=$(read_opt ollama_url "")
OLLAMA_MODEL=$(read_opt ollama_model "llama3.2")
DEFAULT_PROVIDER=$(read_opt default_provider "ollama")
TTS_ENGINE=$(read_opt tts_engine "tts.piper")
LOG_LEVEL=$(read_opt log_level "INFO")

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
exec python3 -m clanker.main
