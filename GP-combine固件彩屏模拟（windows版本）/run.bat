@echo off
setlocal
set "SIM=%~dp0"
if "%SIM:~-1%"=="\" set "SIM=%SIM:~0,-1%"

set "ARG=%~1"
if "%ARG%"=="" set "ARG=240"
if /i "%ARG%"=="240" set "NAME=esp32"
if /i "%ARG%"=="320" set "NAME=esp32_170x320"
if /i "%ARG%"=="172" set "NAME=esp32_172x320"
if not defined NAME set "NAME=%ARG%"

set "REST="
:parse
if "%~2"=="" goto :run
set "REST=%REST% %~2"
shift
goto :parse

:run
set "BIN=%SIM%\build\sim_%NAME%.exe"
if not exist "%BIN%" (
  echo [run] not built yet: run build.bat %ARG% first
  exit /b 1
)
"%BIN%"%REST%