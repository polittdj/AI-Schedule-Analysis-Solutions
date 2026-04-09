@echo off
echo Starting Schedule Forensics Local Tool...
echo.
echo Checking dependencies...
python --version >nul 2>&1 || (echo ERROR: Python not found. Install Python 3.12+ && pause && exit /b 1)
java -version >nul 2>&1 || (echo ERROR: Java not found. Install OpenJDK 11+ && pause && exit /b 1)
echo.
echo Installing Python dependencies...
pip install -r requirements.txt --quiet
echo.
echo Starting web server on http://localhost:5000
echo Press Ctrl+C to stop
echo.
python -m app.main
