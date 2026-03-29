# HelioX Setup Script (Windows PowerShell)

# 1. Check for Python
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Python is not installed. Please install Python 3.10+ and add it to your PATH." -ForegroundColor Red
    exit
}

# 2. Create Virtual Environment
Write-Host "Creating virtual environment..." -ForegroundColor Cyan
python -m venv .venv

# 3. Upgrade Pip
Write-Host "Upgrading pip..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip

# 4. Install Requirements
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Cyan
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

# 5. Success
Write-Host "`nSetup Complete! To start the API server, run: .\run_api.ps1" -ForegroundColor Green
