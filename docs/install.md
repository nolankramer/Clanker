# Installation

## Prerequisites

- **Python 3.12+**
- **Home Assistant** with a [long-lived access token](https://www.home-assistant.io/docs/authentication/#your-account-profile)
- **Docker** (recommended) or bare-metal Python
- (Optional) **Ollama** for local LLM inference
- (Optional) **Frigate** for camera event detection
- (Optional) **Double Take** for face recognition

## Docker Setup

```bash
git clone https://github.com/nolankramer/clanker.git
cd clanker

cp .env.example .env
# Edit .env — set CLANKER_HA_URL, CLANKER_HA_TOKEN, and any API keys

cp config/clanker.yaml.example config/clanker.yaml
# Edit config/clanker.yaml — set room/speaker/sensor mappings

docker compose up -d
```

## Bare Metal Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/nolankramer/clanker.git
cd clanker

uv sync

cp .env.example .env
cp config/clanker.yaml.example config/clanker.yaml
# Edit both files

uv run clanker
```

## Systemd Service (alternative to Docker)

Create `/etc/systemd/system/clanker.service`:

```ini
[Unit]
Description=Clanker Smart Home Assistant
After=network.target

[Service]
Type=simple
User=clanker
WorkingDirectory=/opt/clanker
EnvironmentFile=/opt/clanker/.env
ExecStart=/opt/clanker/.venv/bin/python -m clanker.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now clanker
```
