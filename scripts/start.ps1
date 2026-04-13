# Schedule Forensics Local Tool — Windows PowerShell launcher
#
# Checks for Python 3.11+ and Java 17+, creates/activates a .venv,
# installs the pinned requirements, and starts the Flask dev server
# on http://localhost:5000.
#
# Usage (from the repository root):
#   PowerShell -ExecutionPolicy Bypass -File scripts\start.ps1
#
# Or, if execution policy is already relaxed:
#   .\scripts\start.ps1

$ErrorActionPreference = "Stop"

# -------------------------------------------------------------------- #
# Repo root resolution
# -------------------------------------------------------------------- #
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot  = Split-Path -Parent $scriptDir
Set-Location $repoRoot

Write-Host ""
Write-Host "Schedule Forensics Local Tool" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Cyan
Write-Host ""

# -------------------------------------------------------------------- #
# Python 3.11+ check
# -------------------------------------------------------------------- #
Write-Host "Checking Python..." -ForegroundColor Yellow

$pythonCmd = $null
foreach ($candidate in @("python", "py -3", "python3")) {
    try {
        $ver = & cmd /c "$candidate --version 2>&1"
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python\s+(\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 11) {
                $pythonCmd = $candidate
                Write-Host "  Found $ver" -ForegroundColor Green
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $pythonCmd) {
    Write-Host "ERROR: Python 3.11 or newer was not found on PATH." -ForegroundColor Red
    Write-Host "       Install from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
    exit 1
}

# -------------------------------------------------------------------- #
# Java 17+ check
# -------------------------------------------------------------------- #
Write-Host "Checking Java..." -ForegroundColor Yellow
try {
    $javaVersion = & cmd /c "java -version 2>&1"
    if ($LASTEXITCODE -ne 0) { throw "java exited non-zero" }
    $versionLine = ($javaVersion | Select-Object -First 1)
    if ($versionLine -match '"(\d+)(?:\.(\d+))?') {
        $javaMajor = [int]$Matches[1]
        if ($javaMajor -lt 17) {
            Write-Host "ERROR: Java $javaMajor detected; Java 17 or newer is required for MPXJ." -ForegroundColor Red
            exit 1
        }
        Write-Host "  Found $versionLine" -ForegroundColor Green
    } else {
        Write-Host "WARNING: Could not parse Java version from: $versionLine" -ForegroundColor Yellow
    }
} catch {
    Write-Host "ERROR: Java was not found on PATH." -ForegroundColor Red
    Write-Host "       Install OpenJDK 17+ from https://adoptium.net/ and re-run." -ForegroundColor Red
    exit 1
}

# -------------------------------------------------------------------- #
# Virtual environment bootstrap
# -------------------------------------------------------------------- #
$venvPath = Join-Path $repoRoot ".venv"
$venvActivate = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment in .venv..." -ForegroundColor Yellow
    & cmd /c "$pythonCmd -m venv .venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Done." -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists." -ForegroundColor Green
}

Write-Host "Activating virtual environment..." -ForegroundColor Yellow
. $venvActivate

# -------------------------------------------------------------------- #
# Install dependencies
# -------------------------------------------------------------------- #
Write-Host "Installing pinned dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip | Out-Null
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed." -ForegroundColor Red
    exit 1
}

# -------------------------------------------------------------------- #
# Launch the app
# -------------------------------------------------------------------- #
Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " Starting Schedule Forensics on:" -ForegroundColor Cyan
Write-Host "   http://localhost:5000" -ForegroundColor Green
Write-Host ""
Write-Host " Press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host ""

python -m app
