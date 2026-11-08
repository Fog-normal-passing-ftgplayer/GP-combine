@echo off
rem Build Windows build of GP-Fusion Wizard (ASCII-only for encoding safety)
setlocal enabledelayedexpansion
cd /d %~dp0

rem ---- find Python ----
set "PYCMD="
where py >nul 2>nul
if not errorlevel 1 (
  for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PYCMD=%%i"
)
if not defined PYCMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  echo [ERROR] Python 3.10+ not found. Install it and check "Add python.exe to PATH".
  pause
  exit /b 1
)

rem ---- check 64-bit ----
"%PYCMD%" -c "import struct; exit(0 if struct.calcsize('P')*8==64 else 1)" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Need 64-bit Python, 32-bit Python is not supported.
  pause
  exit /b 1
)

echo [1/4] Creating virtual environment...
if not exist .venv (
  "%PYCMD%" -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies (PySide6 ~200MB, first run is slow)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo [ERROR] Dependency install failed. Check network.
  pause
  exit /b 1
)

echo [3/4] Building executable...
python -m PyInstaller --clean --noconfirm gpfusion.spec > build_log.txt 2>&1
if errorlevel 1 (
  echo [ERROR] Build failed. Last 30 lines of build_log.txt:
  powershell -NoProfile -Command "Get-Content build_log.txt -Tail 30"
  echo.
  echo Full log saved to build_log.txt - send it to the developer for help.
  pause
  exit /b 1
)

echo [4/4] Creating zip...
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\GPFusionWizard' -DestinationPath 'dist\GPFusionWizard-windows.zip'"

echo.
echo Done!
echo Run folder : dist\GPFusionWizard\  (copy the whole folder)
echo Zip        : dist\GPFusionWizard-windows.zip
echo.
echo If the app fails to start, send dist\GPFusionWizard\gpfusion_crash.log
pause
