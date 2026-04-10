#!/usr/bin/env bashset -euo pipefail

echo "=== Clanker Add-on Starting ==="

# HA Supervisor provides these automatically
HA_TOKEN="${SUPERVISOR_TOKEN:-}"
HA_URL="http://supervisor/core"

# Read add-on options from HA
OPTIONS_FILE="/data/options.json"
if [ ! -f "$OPTIONS_FILE" ]; then
    echo "ERROR: Options file not found at $OPTIONS_FILE"
    exit 1
fi

# Parse options with Python
ANTHROPIC_KEY=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('anthropic_api_key', ''))")
OPENAI_KEY=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('openai_api_key', ''))")
OLLAMA_URL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('ollama_url', 'http://localhost:11434'))")
OLLAMA_MODEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('ollama_model', 'llama3.2'))")
DEFAULT_PROVIDER=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('default_provider', 'anthropic'))")
VISION_PROVIDER=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('vision_provider', 'anthropic'))")
TTS_ENGINE=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('tts_engine', 'tts.piper'))")
FRIGATE_ENABLED=$(python3 -c "import json; print(str(json.load(open('$OPTIONS_FILE')).get('frigate_enabled', False)).lower())")
FRIGATE_URL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('frigate_url', 'http://localhost:5000'))")
LOG_LEVEL=$(python3 -c "import json; print(json.load(open('$OPTIONS_FILE')).get('log_level', 'INFO'))")

# --- Install custom component into HA ---
COMPONENT_SRC="/ha_custom_component"
COMPONENT_DST="/config/custom_components/clanker"

if [ -d "$COMPONENT_SRC" ]; then
    echo "Installing Clanker HA custom component..."
    mkdir -p "$(dirname "$COMPONENT_DST")"
    rm -rf "$COMPONENT_DST"
    cp -r "$COMPONENT_SRC" "$COMPONENT_DST"
    echo "Custom component installed at $COMPONENT_DST"
else
    echo "WARNING: Custom component source not found"
fi

# --- Generate config ---
mkdir -p /app/config

cat > /app/config/clanker.yaml << YAML
ha:
  url: "${HA_URL}"

anthropic:
  model: "claude-sonnet-4-20250514"
  max_tokens: 4096

ollama:
  base_url: "${OLLAMA_URL}"
  model: "${OLLAMA_MODEL}"
  max_tokens: 4096

task_routes:
  - task: vision
    provider: ${VISION_PROVIDER}
  - task: reasoning
    provider: ${DEFAULT_PROVIDER}
  - task: quick_intent
    provider: ollama
  - task: summarization
    provider: ollama
  - task: conversation
    provider: ${DEFAULT_PROVIDER}

default_provider: ${DEFAULT_PROVIDER}

memory:
  db_path: "/data/clanker.db"
  markdown_dir: "/data/memory"
  chromadb_path: "/data/chroma"

conversation:
  host: "0.0.0.0"
  port: 8472
  tts_engine: "${TTS_ENGINE}"

frigate:
  enabled: ${FRIGATE_ENABLED}
  url: "${FRIGATE_URL}"

log_level: ${LOG_LEVEL}
YAML

# --- Generate .env ---
cat > /app/.env << ENV
CLANKER_HA__TOKEN=${HA_TOKEN}
ENV

if [ -n "$ANTHROPIC_KEY" ]; then
    echo "CLANKER_ANTHROPIC__API_KEY=${ANTHROPIC_KEY}" >> /app/.env
fi
if [ -n "$OPENAI_KEY" ]; then
    echo "CLANKER_OPENAI__API_KEY=${OPENAI_KEY}" >> /app/.env
fi

# --- Add clanker entry to HA configuration.yaml if not present ---
HA_CONFIG="/config/configuration.yaml"
if [ -f "$HA_CONFIG" ] && ! grep -q "clanker:" "$HA_CONFIG"; then
    echo "" >> "$HA_CONFIG"
    echo 'clanker:' >> "$HA_CONFIG"
    echo '  url: "http://localhost:8472"' >> "$HA_CONFIG"
    echo "Added clanker entry to HA configuration.yaml"
fi

echo "=== Configuration generated ==="
echo "HA URL: ${HA_URL}"
echo "Default provider: ${DEFAULT_PROVIDER}"
echo "Ollama: ${OLLAMA_URL} (${OLLAMA_MODEL})"
echo "Frigate: ${FRIGATE_ENABLED}"
echo "Log level: ${LOG_LEVEL}"
echo "=== Starting Clanker ==="

cd /app
exec python3 -m clanker.main
