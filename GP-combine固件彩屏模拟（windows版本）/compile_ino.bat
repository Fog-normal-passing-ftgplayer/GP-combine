@echo off
REM ===========================================================================
REM  Generate sketch/<name>.ino.cpp with arduino-cli (slow, minutes).
REM  (ASCII-only on purpose)
REM
REM  Kept separate from build.bat: the ESP32 toolchain is slow, while building
REM  the simulator takes seconds. Splitting them means editing sim_main.cpp
REM  never waits for the toolchain, and a stale .ino.cpp can never slip through
REM  silently.
REM
REM    compile_ino.bat            all three variants
REM    compile_ino.bat 240        240x135
REM    compile_ino.bat 320        170x320
REM    compile_ino.bat 172        172x320
REM ===========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "SIM=%~dp0"
if "%SIM:~-1%"=="\" set "SIM=%SIM:~0,-1%"
for %%I in ("%SIM%\..") do set "REPO=%%~fI"
if not exist "%REPO%\esp32" for %%I in ("%SIM%\..\..") do set "REPO=%%~fI"
set "FQBN=esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom"

set "ARG=%~1"
if "%ARG%"=="" set "ARG=all"
if /i "%ARG%"=="-h"     goto :usage
if /i "%ARG%"=="--help" goto :usage

call :find_cli
if not defined CLI (
  echo [ino] arduino-cli not found.
  echo       install it, then: arduino-cli core install esp32:esp32
  exit /b 1
)

if /i "%ARG%"=="240" (call :one esp32         & goto :done)
if /i "%ARG%"=="320" (call :one esp32_170x320 & goto :done)
if /i "%ARG%"=="172" (call :one esp32_172x320 & goto :done)
if /i "%ARG%"=="all" (
  call :one esp32
  call :one esp32_170x320
  call :one esp32_172x320
  goto :done
)
echo [ino] usage: compile_ino.bat [240^|320^|172^|all]
exit /b 1

:done
echo [ino] done. Now run build.bat ^(or build.bat 320 / 172^).
exit /b 0

REM ===========================================================================
:one
set "SK=%~1"
set "BUILD=%SIM%\build\%SK%"
set "SRC=%BUILD%\sketch\%SK%.ino.cpp"
if not exist "%BUILD%" mkdir "%BUILD%"
echo [ino] %SK%: running arduino-cli ^(minutes^)...
"%CLI%" compile --fqbn "%FQBN%" --build-path "%BUILD%" "%REPO%\%SK%" || (echo [ino] failed: %SK% & exit /b 1)
if not exist "%SRC%" (echo [ino] missing output: %SRC% & exit /b 1)
REM content hash of the sketch sources, so build.bat can detect staleness
rem (mtime is unreliable: arduino-cli caches and may not rewrite unchanged output)
set "HF=%TEMP%\gp_ino_%RANDOM%%RANDOM%.txt"
type "%REPO%\%SK%\*.ino" > "%HF%" 2>nul
type "%REPO%\%SK%\*.h"  >> "%HF%" 2>nul
set "SH="
for /f "usebackq skip=1 delims=" %%H in (`certutil -hashfile "%HF%" SHA256`) do if not defined SH set "SH=%%H"
del "%HF%" >nul 2>&1
if defined SH > "%BUILD%\.ino_src_hash" echo !SH!
echo [ino] ok: %SRC%
exit /b 0

:find_cli
set "CLI="
where arduino-cli >nul 2>&1 && set "CLI=arduino-cli"
if not defined CLI if exist "%LOCALAPPDATA%\Arduino15\arduino-cli.exe" set "CLI=%LOCALAPPDATA%\Arduino15\arduino-cli.exe"
if not defined CLI if exist "%ProgramFiles%\Arduino CLI\arduino-cli.exe" set "CLI=%ProgramFiles%\Arduino CLI\arduino-cli.exe"
exit /b 0

:usage
echo usage: compile_ino.bat [240^|320^|172^|all]
exit /b 0
