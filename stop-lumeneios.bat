@echo off
rem ============================================================================================
rem  LumenEIOS - double-click to STOP everything: all backend servers (which unloads the Qwen model
rem  and frees the GPU) and all frontends, including ones left running by earlier sessions.
rem ============================================================================================
setlocal EnableExtensions
title Stop LumenEIOS
set "WSL_DISTRO=Ubuntu"
set "FALLBACK_APP_DIR=/home/agam/DP/arena/apps/lumeneios"

where wsl.exe >nul 2>nul
if errorlevel 1 (
    echo WSL was not found on this computer.
    pause
    exit /b 1
)
set "DISTRO_ARG=-d %WSL_DISTRO%"
wsl.exe %DISTRO_ARG% -- true >nul 2>nul
if errorlevel 1 set "DISTRO_ARG="

rem Prefer the copy of the project this file sits in; otherwise use the fallback path.
rem Opened from Explorer at \\wsl.localhost\<distro>\... (or \\wsl$\<distro>\...) the folder is already inside
rem WSL: translate it directly - wslpath turns such UNC paths into a non-existent /mnt/c/... folder.
set "APP_DIR="
set "HERE=%~dp0"
if /i "%HERE:~0,16%"=="\\wsl.localhost\" set "UNC_REST=%HERE:~16%"
if /i "%HERE:~0,7%"=="\\wsl$\" set "UNC_REST=%HERE:~7%"
if defined UNC_REST (
    for /f "tokens=1,* delims=\" %%A in ("%UNC_REST%") do set "APP_DIR=/%%B"
) else if exist "%~dp0scripts\stop-all.sh" (
    for /f "usebackq delims=" %%P in (`wsl.exe %DISTRO_ARG% -- wslpath -a "%~dp0."`) do set "APP_DIR=%%P"
)
if defined APP_DIR set "APP_DIR=%APP_DIR:\=/%"
if defined APP_DIR if "%APP_DIR:~-1%"=="/" set "APP_DIR=%APP_DIR:~0,-1%"
rem Use it only if it really is the project; otherwise fall back.
if defined APP_DIR (
    wsl.exe %DISTRO_ARG% -- test -f "%APP_DIR%/scripts/stop-all.sh"
    if errorlevel 1 set "APP_DIR="
)
if not defined APP_DIR set "APP_DIR=%FALLBACK_APP_DIR%"
wsl.exe %DISTRO_ARG% --cd "%APP_DIR%" -- bash scripts/stop-all.sh
echo.
pause
