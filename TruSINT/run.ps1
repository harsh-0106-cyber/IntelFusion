# TruSINT — One-Click Launcher
# Run this script from the project root to install deps and start the server.

Write-Host ""
Write-Host "  ████████████████████████████████████████" -ForegroundColor Cyan
Write-Host "  █     TruSINT  OSINT  Search  Engine   █" -ForegroundColor Cyan
Write-Host "  ████████████████████████████████████████" -ForegroundColor Cyan
Write-Host ""

$backendDir = Join-Path $PSScriptRoot "backend"

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] Python is not installed or not on PATH." -ForegroundColor Red
    Write-Host "  Install from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$pythonVersion = python --version 2>&1
Write-Host "[OK] Found: $pythonVersion" -ForegroundColor Green

# Check/create virtual environment
$venvPath = Join-Path $backendDir ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
}

# Activate venv
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
} else {
    Write-Host "[WARN] Could not activate venv. Trying system Python." -ForegroundColor Yellow
}

# Install dependencies
Write-Host "[INFO] Installing dependencies..." -ForegroundColor Yellow
pip install -r (Join-Path $backendDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies." -ForegroundColor Red
    exit 1
}
Write-Host "[OK] Dependencies installed." -ForegroundColor Green

# Copy .env if not exists
$envFile = Join-Path $backendDir ".env"
$envExample = Join-Path $backendDir ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $envExample)) {
    Copy-Item $envExample $envFile
    Write-Host "[INFO] Created .env from .env.example" -ForegroundColor Yellow
}

# Start Flask
Write-Host ""
Write-Host "  Starting TruSINT on http://localhost:5000 ..." -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

Set-Location $backendDir
python app.py
