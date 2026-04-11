# Clanker - Windows installer
#
# Usage (PowerShell):
#   irm https://raw.githubusercontent.com/nolankramer/clanker/main/install.ps1 | iex
#
# What it does:
#   1. Checks prerequisites (Python 3.11+, git)
#   2. Installs uv if needed
#   3. Clones the repo (or pulls if exists)
#   4. Installs dependencies
#   5. Launches the setup wizard (handles .env + config - no manual editing)
#
$ErrorActionPreference = "Stop"

$REPO = "https://github.com/nolankramer/clanker.git"
if ($env:CLANKER_DIR) { $INSTALL_DIR = $env:CLANKER_DIR } else { $INSTALL_DIR = Join-Path $HOME "clanker" }

function Write-Step($msg) { Write-Host ("`n=== " + $msg + " ===") -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host ("  [OK] " + $msg) -ForegroundColor Green }
function Write-Fail($msg)  { Write-Host ("  [FAIL] " + $msg) -ForegroundColor Red }

Write-Host ""
Write-Host "  Clanker Installer" -ForegroundColor Cyan
Write-Host "  LLM-powered smart home assistant" -ForegroundColor DarkGray
Write-Host ""

# --- Check prerequisites ---
Write-Step "Checking prerequisites"

# Python
try {
    $pyVersion = & python --version 2>&1
    if ($pyVersion -match 'Python (\d+)\.(\d+)') {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 11) {
            Write-Ok ("Python " + $Matches[0])
        } else {
            Write-Fail ("Python " + $Matches[0] + " found, but 3.11+ required")
            Write-Host "  Download from https://www.python.org/downloads/" -ForegroundColor Yellow
            exit 1
        }
    }
} catch {
    Write-Fail "Python not found. Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
}

# Git
try {
    $gitVersion = & git --version 2>&1
    Write-Ok ("git " + ($gitVersion -replace 'git version ',''))
} catch {
    Write-Fail "git not found. Install from https://git-scm.com/download/win"
    exit 1
}

# --- Install uv ---
Write-Step "Installing uv"
try {
    $uvVersion = & uv --version 2>&1
    Write-Ok ("uv already installed (" + $uvVersion + ")")
} catch {
    Write-Host "  Installing uv..." -ForegroundColor DarkGray
    irm https://astral.sh/uv/install.ps1 | iex
    # Refresh PATH
    $localBin = Join-Path $HOME ".local\bin"
    $cargoBin = Join-Path $HOME ".cargo\bin"
    $env:PATH = $localBin + ";" + $cargoBin + ";" + $env:PATH
    Write-Ok "uv installed"
}

# --- Clone or update ---
Write-Step "Getting Clanker"
$gitDir = Join-Path $INSTALL_DIR ".git"
$prevPref = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
if (Test-Path $gitDir) {
    Write-Ok ("Found existing install at " + $INSTALL_DIR)
    Push-Location $INSTALL_DIR
    & git pull --ff-only origin main 2>&1 | Out-Null
    Write-Ok "Updated to latest"
} else {
    & git clone $REPO $INSTALL_DIR 2>&1 | Out-Null
    Push-Location $INSTALL_DIR
    Write-Ok ("Cloned to " + $INSTALL_DIR)
}
$ErrorActionPreference = $prevPref

# --- Install dependencies ---
Write-Step "Installing dependencies"
$prevPref = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& uv sync 2>&1 | Out-Null
$ErrorActionPreference = $prevPref
Write-Ok "Dependencies installed"

# --- Done ---
Write-Step "Installation complete!"
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor White
Write-Host ""
Write-Host ("  cd " + $INSTALL_DIR) -ForegroundColor Cyan
Write-Host "  uv run clanker-setup          # CLI setup wizard" -ForegroundColor Cyan
Write-Host "  uv run clanker-setup --web    # browser-based wizard" -ForegroundColor Cyan
Write-Host ""
Write-Host "  The wizard handles everything - API keys, config," -ForegroundColor DarkGray
Write-Host "  Ollama setup, voice pipeline. No manual file editing." -ForegroundColor DarkGray
Write-Host ""

# --- Offer to run setup ---
Write-Host "  Run the setup wizard now?" -ForegroundColor White
Write-Host "    1) Browser-based (recommended)" -ForegroundColor Cyan
Write-Host "    2) CLI (terminal)" -ForegroundColor Cyan
Write-Host "    3) Skip" -ForegroundColor DarkGray
Write-Host ""
$answer = Read-Host "  Choice (1/2/3)"
if ($answer -eq "2") {
    Write-Host ""
    & uv run clanker-setup
} elseif ($answer -ne "3") {
    Write-Host ""
    & uv run clanker-setup --web
}

Pop-Location
