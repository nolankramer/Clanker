#!/usr/bin/env bash
# Clanker appliance provisioner
#
# Transforms a fresh Ubuntu 24.04 (Server or Desktop) into a
# fully configured Clanker smart home appliance.
#
# What it installs:
#   - Docker + Docker Compose
#   - Home Assistant (container)
#   - Ollama (local LLM inference)
#   - Clanker + all voice add-ons
#   - mDNS (avahi) so the device is reachable at clanker.local
#   - First-boot web wizard on port 80
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nolankramer/clanker/main/image/provision.sh | sudo bash
#
# Or used by the image builder to pre-configure an OS image.
#
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

CYAN='\033[96m'
GREEN='\033[92m'
RED='\033[91m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

log()  { echo -e "${GREEN}[clanker]${RESET} $1"; }
err()  { echo -e "${RED}[clanker]${RESET} $1" >&2; }
step() { echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (use sudo)"
    exit 1
fi

step "Updating system"
apt-get update -qq
apt-get upgrade -y -qq

step "Installing base packages"
apt-get install -y -qq \
    curl wget git ca-certificates gnupg lsb-release \
    avahi-daemon avahi-utils \
    python3 python3-pip python3-venv \
    jq unzip

# ---- Docker ----
step "Installing Docker"
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
        gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    log "Docker installed"
else
    log "Docker already installed"
fi

# ---- Home Assistant ----
step "Installing Home Assistant"
HA_DIR="/opt/homeassistant"
mkdir -p "$HA_DIR"

if ! docker ps -a --format '{{.Names}}' | grep -q homeassistant; then
    docker run -d \
        --name homeassistant \
        --restart unless-stopped \
        --privileged \
        --network host \
        -v "$HA_DIR:/config" \
        -v /run/dbus:/run/dbus:ro \
        ghcr.io/home-assistant/home-assistant:stable
    log "Home Assistant started at http://localhost:8123"
else
    log "Home Assistant already running"
fi

# ---- Ollama ----
step "Installing Ollama"
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    log "Ollama installed"
else
    log "Ollama already installed"
fi

# Pull default models in background
log "Pulling default LLM models (background)..."
(ollama pull llama3.2 2>/dev/null || true) &
(ollama pull nomic-embed-text 2>/dev/null || true) &

# ---- Clanker ----
step "Installing Clanker"
CLANKER_DIR="/opt/clanker"

if [ ! -d "$CLANKER_DIR/.git" ]; then
    git clone https://github.com/nolankramer/clanker.git "$CLANKER_DIR"
else
    cd "$CLANKER_DIR" && git pull --ff-only origin main 2>/dev/null || true
fi

# Install uv
if ! command -v uv &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="/root/.local/bin:$PATH"
fi

cd "$CLANKER_DIR"
uv sync 2>/dev/null
log "Clanker installed at $CLANKER_DIR"

# ---- mDNS ----
step "Configuring mDNS (clanker.local)"
hostnamectl set-hostname clanker 2>/dev/null || true
systemctl enable avahi-daemon
systemctl restart avahi-daemon
log "Device reachable at clanker.local"

# ---- First-boot wizard service ----
step "Setting up first-boot wizard"
cat > /etc/systemd/system/clanker-setup.service << 'UNIT'
[Unit]
Description=Clanker First-Boot Setup Wizard
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/clanker
ExecStart=/root/.local/bin/uv run clanker-setup --web --port 80
Restart=on-failure
RestartSec=5
Environment=PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
UNIT

# Only enable the wizard service — it runs until the user completes setup
systemctl daemon-reload
systemctl enable clanker-setup.service

# ---- Clanker main service (starts after setup is complete) ----
cat > /etc/systemd/system/clanker.service << 'UNIT'
[Unit]
Description=Clanker Smart Home Assistant
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/clanker
ExecStart=/root/.local/bin/uv run clanker
Restart=always
RestartSec=10
Environment=PATH=/root/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
# Don't enable clanker.service yet — setup wizard does this after config is saved

# ---- Post-setup script (called by wizard after config is saved) ----
cat > /opt/clanker/activate.sh << 'ACTIVATE'
#!/usr/bin/env bash
# Called by the setup wizard after configuration is complete.
# Stops the wizard, installs the HA component, and starts Clanker.
set -euo pipefail

echo "Activating Clanker..."

# Install HA custom component
HA_COMPONENTS="/opt/homeassistant/custom_components"
mkdir -p "$HA_COMPONENTS"
cp -r /opt/clanker/ha_component/custom_components/clanker "$HA_COMPONENTS/clanker"

# Add clanker entry to HA config if not present
HA_CONFIG="/opt/homeassistant/configuration.yaml"
if [ -f "$HA_CONFIG" ] && ! grep -q "clanker:" "$HA_CONFIG"; then
    echo -e '\nclanker:\n  url: "http://localhost:8472"' >> "$HA_CONFIG"
fi

# Restart HA to pick up the component
docker restart homeassistant 2>/dev/null || true

# Stop the setup wizard, start Clanker
systemctl disable clanker-setup.service
systemctl stop clanker-setup.service
systemctl enable clanker.service
systemctl start clanker.service

echo "Clanker is running! Setup wizard has been disabled."
echo "Access Home Assistant at http://clanker.local:8123"
ACTIVATE
chmod +x /opt/clanker/activate.sh

# ---- Wait for background model pulls ----
wait 2>/dev/null || true

# ---- Done ----
step "Provisioning complete!"
echo ""
echo -e "  ${BOLD}The device will be available at:${RESET}"
echo -e "  ${CYAN}http://clanker.local${RESET}      ${DIM}— Setup wizard${RESET}"
echo -e "  ${CYAN}http://clanker.local:8123${RESET}  ${DIM}— Home Assistant${RESET}"
echo ""
echo -e "  ${DIM}On first boot, open http://clanker.local in your browser${RESET}"
echo -e "  ${DIM}to walk through the setup wizard.${RESET}"
echo ""
