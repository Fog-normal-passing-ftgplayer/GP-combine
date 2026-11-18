@echo off
REM ===========================================================================
REM  GP-Combine UI simulator - Windows build script
REM  (ASCII-only on purpose: non-ASCII in .bat breaks under some code pages)
REM
REM    build.bat              240x135  (esp32/)
REM    build.bat 320          170x320  (esp32_170x320/)
REM    build.bat 172          172x320  (esp32_172x320/)
REM    build.bat --check      only check the toolchain, do not build
REM    AUTO_INO=1 build.bat   run arduino-cli when .ino.cpp is missing/stale
REM
REM  Needs Visual Studio 2019/2022 with "Desktop development with C++",
REM  or MinGW-w64 g++ on PATH (fallback).
REM ===========================================================================
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "SIM=%~dp0"
if "%SIM:~-1%"=="\" set "SIM=%SIM:~0,-1%"
for %%I in ("%SIM%\..") do set "REPO=%%~fI"
if not exist "%REPO%\esp32" for %%I in ("%SIM%\..\..") do set "REPO=%%~fI"
set "FQBN=esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=custom"

REM ---- pick variant (SKETCH env var overrides everything) -------------------
REM keep the old SKETCH=<dir> override working (must capture before we assign it)
if defined SKETCH set "GP_SKETCH=%SKETCH%"
set "ARG=%~1"
if "%ARG%"=="" set "ARG=240"
if /i "%ARG%"=="--check" goto :check
if /i "%ARG%"=="-h"      goto :usage
if /i "%ARG%"=="--help"  goto :usage
if /i "%ARG%"=="240" (set "DEF=%REPO%\esp32"         & set "TAG=240" & goto :picked)
if /i "%ARG%"=="320" (set "DEF=%REPO%\esp32_170x320" & set "TAG=320" & goto :picked)
if /i "%ARG%"=="172" (set "DEF=%REPO%\esp32_172x320" & set "TAG=172" & goto :picked)
set "DEF=%ARG%"
set "TAG=%ARG%"
:picked
if defined GP_SKETCH set "DEF=%GP_SKETCH%"
set "SKETCH=%DEF%"
if not exist "%SKETCH%\" (echo [build] sketch dir not found: %SKETCH% & exit /b 1)
for %%I in ("%SKETCH%") do set "NAME=%%~nxI"

set "BUILD=%SIM%\build\%NAME%"
set "GEN=%SIM%\build\gen"
set "SRC=%BUILD%\sketch\%NAME%.ino.cpp"
set "STAMP=%BUILD%\.ino_src_hash"
if not exist "%BUILD%" mkdir "%BUILD%"
if not exist "%GEN%"   mkdir "%GEN%"

echo [build] %NAME%   %SKETCH%

REM ---- 1) .ino.cpp present and up to date? ---------------------------------
call :src_hash
set "NEED_INO=0"
if not exist "%SRC%" set "NEED_INO=1"
if "%NEED_INO%"=="0" if not "%SRCHASH%"=="none" if exist "%STAMP%" (
  set /p "OLDHASH="<"%STAMP%"
  if not "!OLDHASH!"=="!SRCHASH!" set "NEED_INO=1"
)
if "%NEED_INO%"=="1" (
  if "%AUTO_INO%"=="1" goto :gen_ino
  echo [build] .ino.cpp is missing or stale. Generate it once:
  echo          arduino-cli compile --fqbn "%FQBN%" --build-path "%BUILD%" "%SKETCH%"
  echo         or:  set AUTO_INO=1 ^&^& build.bat %ARG%
  exit /b 1
)
goto :ino_ready

:gen_ino
call :find_cli
echo [build] running arduino-cli (takes minutes)...
"!CLI!" compile --fqbn "%FQBN%" --build-path "%BUILD%" "%SKETCH%" || (echo [build] arduino-cli failed & exit /b 1)
> "%STAMP%" echo !SRCHASH!

:ino_ready
copy /Y "%SRC%" "%GEN%\esp32.ino.cpp" >nul || (echo [build] copy ino.cpp failed & exit /b 1)

REM ---- 2) screen size straight from the firmware ---------------------------
set "SIM_W=240"
set "SIM_H=135"
for /f "tokens=3" %%a in ('findstr /B /C:"#define SCR_W" "%SRC%" 2^>nul') do set "SIM_W=%%a"
for /f "tokens=3" %%a in ('findstr /B /C:"#define SCR_H" "%SRC%" 2^>nul') do set "SIM_H=%%a"

REM ---- 3) toolchain --------------------------------------------------------
set "CC_KIND="
call :find_msvc
if defined VCVARS (set "CC_KIND=msvc") else (where g++ >nul 2>&1 && set "CC_KIND=mingw")
if not defined CC_KIND (
  echo [build] no compiler found.
  echo         Install Visual Studio 2019/2022 C++ desktop workload,
  echo         or put MinGW-w64 g++ on PATH.
  exit /b 1
)

echo [build] %SIM_W%x%SIM_H%   toolchain: %CC_KIND%
if "%CC_KIND%"=="mingw" goto :build_mingw

:build_msvc
call "%VCVARS%" >nul || (echo [build] vcvars64.bat failed & exit /b 1)
where cl >nul 2>&1 || (echo [build] cl not found after vcvars & exit /b 1)
REM response file keeps paths with spaces safe
set "RSP=%BUILD%\sources.rsp"
> "%RSP%" echo /nologo
>> "%RSP%" echo /std:c++17 /O2 /w /EHsc /utf-8
>> "%RSP%" echo /DSIM_IMG_W=%SIM_W% /DSIM_IMG_H=%SIM_H%
>> "%RSP%" echo /I "%SIM%\shim" /I "%SKETCH%" /I "%GEN%"
>> "%RSP%" echo /Fo"%BUILD%\\"
>> "%RSP%" echo /Fe"%SIM%\build\sim_%NAME%.exe"
>> "%RSP%" echo "%SIM%\sim_main.cpp"
if exist "%SKETCH%\src" for /r "%SKETCH%\src" %%F in (*.cpp) do >> "%RSP%" echo "%%F"
>> "%RSP%" echo user32.lib gdi32.lib gdiplus.lib
cl @"%RSP%" || (echo [build] compile failed & exit /b 1)
goto :built

:build_mingw
REM response file avoids quoting problems with spaces in paths
set "GRSP=%BUILD%\mingw.rsp"
> "%GRSP%" echo -std=gnu++17 -O2 -w -fno-exceptions -static -static-libgcc -static-libstdc++
>> "%GRSP%" echo -DSIM_IMG_W=%SIM_W% -DSIM_IMG_H=%SIM_H%
>> "%GRSP%" echo -I "%SIM%\shim" -I "%SKETCH%" -I "%GEN%"
>> "%GRSP%" echo "%SIM%\sim_main.cpp"
if exist "%SKETCH%\src" for /r "%SKETCH%\src" %%F in (*.cpp) do >> "%GRSP%" echo "%%F"
>> "%GRSP%" echo -o "%SIM%\build\sim_%NAME%.exe"
>> "%GRSP%" echo -lgdiplus -lgdi32 -luser32
g++ @"%GRSP%" || (echo [build] compile failed & exit /b 1)

:built
echo [build] OK -^> build\sim_%NAME%.exe
echo [build] run: run.bat %ARG% --mode=keys --scale=3
exit /b 0

REM ===========================================================================
:find_cli
set "CLI=arduino-cli"
where arduino-cli >nul 2>&1 && exit /b 0
if exist "%LOCALAPPDATA%\Arduino15\arduino-cli.exe" set "CLI=%LOCALAPPDATA%\Arduino15\arduino-cli.exe"
if exist "%ProgramFiles%\Arduino CLI\arduino-cli.exe" set "CLI=%ProgramFiles%\Arduino CLI\arduino-cli.exe"
exit /b 0

:find_msvc
set "VCVARS="
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" set "VSWHERE=%ProgramFiles%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" exit /b 0
REM let vswhere resolve the real vcvars64.bat: no hardcoded VS versions
for /f "usebackq delims=" %%V in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -find "VC\Auxiliary\Build\vcvars64.bat"`) do set "VCVARS=%%V"
exit /b 0

:src_hash
set "SRCHASH=none"
set "HF=%TEMP%\gp_src_%RANDOM%%RANDOM%.txt"
type "%SKETCH%\*.ino" > "%HF%" 2>nul
type "%SKETCH%\*.h"  >> "%HF%" 2>nul
for /f "usebackq skip=1 delims=" %%H in (`certutil -hashfile "%HF%" SHA256`) do if not defined SH set "SH=%%H"
if defined SH set "SRCHASH=!SH!"
set "SH="
del "%HF%" >nul 2>&1
exit /b 0

:check
echo [check] SIM   = %SIM%
echo [check] REPO  = %REPO%
call :find_msvc
if defined VCVARS (echo [check] MSVC   = !VCVARS!) else (echo [check] MSVC   = not found)
where g++ >nul 2>&1 && (echo [check] MinGW  = found) || (echo [check] MinGW  = not found)
where arduino-cli >nul 2>&1 && (echo [check] CLI    = found) || (echo [check] CLI    = not found ^(only needed with AUTO_INO^))
if exist "%REPO%\esp32\*.ino"         (echo [check] esp32           = ok) else (echo [check] esp32           = MISSING)
if exist "%REPO%\esp32_170x320\*.ino" (echo [check] esp32_170x320   = ok) else (echo [check] esp32_170x320   = MISSING)
if exist "%REPO%\esp32_172x320\*.ino" (echo [check] esp32_172x320   = ok) else (echo [check] esp32_172x320   = MISSING)
exit /b 0

:usage
echo usage: build.bat [240^|320^|172^|--check]
exit /b 0
