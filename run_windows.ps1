# Launcher for VoiceCtl on Windows.
# Run from PowerShell on the Windows host (NOT inside WSL — no audio device).

$env:PYTHONUNBUFFERED = "1"
$env:PYTHONUTF8 = "1"

if (-not (Test-Path .venv)) {
    Write-Host "First run: creating venv and installing dependencies..."
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -e ".[windows]"
}

if (-not (Test-Path .env)) {
    Write-Host "ERROR: .env file not found. Copy .env.example to .env and fill in API keys." -ForegroundColor Red
    exit 1
}

.\.venv\Scripts\python.exe -m app.main
