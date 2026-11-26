@echo off
rem ============================================================================================
rem  LumenEIOS - double-click to start everything: backend API, frontend, and the local Qwen
rem  model on the GPU (inside WSL). The app opens in your browser when it is ready.
rem  Close this window or press Ctrl+C to stop the servers.
rem
rem  Works from inside the repository, or copied anywhere (e.g. the Desktop): it then starts the
rem  project at FALLBACK_APP_DIR below.
rem ============================================================================================
setlocal EnableExtensions
title LumenEIOS
rem WSL distribution that holds the project. If it does not exist, the default distribution is used.
set "WSL_DISTRO=Ubuntu"
set "FALLBACK_APP_DIR=/home/agam/DP/arena/apps/lumeneios"

where wsl.exe >nul 2>nul
if errorlevel 1 (
    echo WSL was not found on this computer. Install it with:  wsl --install
    pause
    exit /b 1
)

set "DISTRO_ARG=-d %WSL_DISTRO%"
wsl.exe %DISTRO_ARG% -- true >nul 2>nul
if errorlevel 1 (
    echo WSL distribution "%WSL_DISTRO%" was not found - using the default distribution.
    set "DISTRO_ARG="
)

rem Prefer the copy of the project this file sits in; otherwise use the fallback path.
rem Opened from Explorer at \\wsl.localhost\<distro>\... (or \\wsl$\<distro>\...) the folder is already inside
rem WSL: translate it directly - wslpath turns such UNC paths into a non-existent /mnt/c/... folder.
set "APP_DIR="
set "HERE=%~dp0"
if /i "%HERE:~0,16%"=="\\wsl.localhost\" set "UNC_REST=%HERE:~16%"
if /i "%HERE:~0,7%"=="\\wsl$\" set "UNC_REST=%HERE:~7%"
if defined UNC_REST (
    for /f "tokens=1,* delims=\" %%A in ("%UNC_REST%") do set "APP_DIR=/%%B"
) else if exist "%~dp0scripts\start-all.sh" (
    for /f "usebackq delims=" %%P in (`wsl.exe %DISTRO_ARG% -- wslpath -a "%~dp0."`) do set "APP_DIR=%%P"
)
if defined APP_DIR set "APP_DIR=%APP_DIR:\=/%"
if defined APP_DIR if "%APP_DIR:~-1%"=="/" set "APP_DIR=%APP_DIR:~0,-1%"
rem Use it only if it really is the project; otherwise fall back.
if defined APP_DIR (
    wsl.exe %DISTRO_ARG% -- test -f "%APP_DIR%/scripts/start-all.sh"
    if errorlevel 1 set "APP_DIR="
)
if not defined APP_DIR set "APP_DIR=%FALLBACK_APP_DIR%"

echo Starting LumenEIOS from %APP_DIR% ...
echo.
wsl.exe %DISTRO_ARG% --cd "%APP_DIR%" -- bash scripts/start-all.sh
echo.
echo LumenEIOS has stopped.
pause
