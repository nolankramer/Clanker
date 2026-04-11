#!/usr/bin/env bash
# Clanker — one-line installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nolankramer/clanker/main/install.sh | bash
#
# What it does:
#   1. Checks prerequisites (Python 3.11+, git)
#   2. Clones the repo (or pulls if it already exists)
#   3. Installs dependencies via uv (installs uv if needed)
#   4. Launches the setup wizard
#
set -euo pipefail

REPO="https://github.com/nolankramer/clanker.git"
INSTALL_DIR="${CLANKER_DIR:-$HOME/clanker}"
CYAN='\033[96m'
GREEN='\033[92m'
RED='\033[91m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { echo -e "  ${GREEN}✓${RESET} $1"; }
warn()  { echo -e "  ${RED}✗${RESET} $1"; }
step()  { echo -e "\n${BOLD}${CYAN}$1${RESET}"; }

echo -e "\n${BOLD}${CYAN}╔════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║         Clanker Installer              ║${RESET}"
echo -e "${BOLD}${CYAN}╚════════════════════════════════════════╝${RESET}"
echo -e "${DIM}  LLM-powered smart home assistant${RESET}\n"

# --- Check prerequisites ---
step "Checking prerequisites..."

# Python
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
        info "Python $PY_VERSION"
    else
        warn "Python $PY_VERSION found, but 3.11+ required"
        exit 1
    fi
else
    warn "Python 3 not found. Install Python 3.11+ first."
    exit 1
fi

# Git
if command -v git &>/dev/null; then
    info "git $(git --version | cut -d' ' -f3)"
else
    warn "git not found. Install git first."
    exit 1
fi

# --- Install uv if needed ---
if ! command -v uv &>/dev/null; then
    step "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    info "uv installed"
else
    info "uv $(uv --version 2>/dev/null | head -1)"
fi

# --- Clone or update repo ---
step "Getting Clanker..."

if [ -d "$INSTALL_DIR/.git" ]; then
    info "Found existing install at $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git pull --ff-only origin main 2>/dev/null || true
    info "Updated to latest"
else
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    info "Cloned to $INSTALL_DIR"
fi

# --- Install dependencies ---
step "Installing dependencies..."
uv sync 2>&1 | tail -1
info "Dependencies installed"

# --- Done ---
step "Installation complete!"
echo ""
echo -e "  ${BOLD}Next steps:${RESET}"
echo ""
echo -e "  ${CYAN}cd $INSTALL_DIR${RESET}"
echo -e "  ${CYAN}uv run clanker-setup${RESET}          ${DIM}# CLI setup wizard${RESET}"
echo -e "  ${CYAN}uv run clanker-setup --web${RESET}    ${DIM}# browser-based wizard${RESET}"
echo ""
echo -e "  ${DIM}Or run directly with Docker:${RESET}"
echo -e "  ${CYAN}docker compose up -d${RESET}"
echo ""

# --- Offer to run setup ---
if [ -t 0 ]; then
    echo -e "  Run the setup wizard now?"
    echo -e "    ${CYAN}1${RESET}) Browser-based (recommended)"
    echo -e "    ${CYAN}2${RESET}) CLI (terminal)"
    echo -e "    ${DIM}3${RESET}) Skip"
    echo ""
    echo -ne "  Choice [1/2/3]: "
    read -r answer
    if [ "$answer" = "2" ]; then
        echo ""
        uv run clanker-setup
    elif [ "$answer" != "3" ]; then
        echo ""
        uv run clanker-setup --web
    fi
fi
