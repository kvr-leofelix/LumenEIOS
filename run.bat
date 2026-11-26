@echo off
rem ============================================================================================
rem  LumenEIOS - double-click to start EVERYTHING on Windows:
rem    * backend API (FastAPI) on http://127.0.0.1:8000
rem    * frontend (Vite)      on http://localhost:3000
rem    * local Qwen2.5-VL model loaded on the GPU, plus a status check of the Gemini fallback and LLM
rem  It picks the Python environment that has CUDA PyTorch (.venv-gpu, then venv, then .venv),
rem  repairs / installs missing packages, frees ports 8000 and 3000 if an old copy is running,
rem  and opens the browser when the backend is ready.
rem
rem  Options (set the variable in the console first, then run run.bat):
rem    NO_WARM=1      do not preload the models (they then load on the first OCR / AI request)
rem    NO_BROWSER=1   do not open the browser
rem    DEV_RELOAD=1   run the backend with --reload (restarts, and reloads the model, on every edit)
rem  Stop everything by closing the two server windows.
rem ============================================================================================
setlocal EnableExtensions
title LumenEIOS launcher
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python and add it to PATH.
    pause
    exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
    echo npm was not found. Install Node.js and add it to PATH.
    pause
    exit /b 1
)

rem ---- 1. choose the Python environment: the first one that has CUDA PyTorch ------------------
set "API_PYTHON="
set "GPU_ENV=0"
for %%E in (.venv-gpu venv .venv) do (
    if not defined API_PYTHON if exist "%%E\Scripts\python.exe" (
        "%%E\Scripts\python.exe" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "API_PYTHON=%CD%\%%E\Scripts\python.exe"
            set "GPU_ENV=1"
        )
    )
)
if not defined API_PYTHON (
    if not exist ".venv\Scripts\python.exe" (
        echo Creating the Python environment .venv ...
        python -m venv .venv
        if errorlevel 1 (
            echo Could not create the Python virtual environment.
            pause
            exit /b 1
        )
    )
    set "API_PYTHON=%CD%\.venv\Scripts\python.exe"
    echo.
    echo WARNING: no Python environment with CUDA PyTorch was found. The local Qwen model cannot load.
    echo          The app still runs; use Gemini as the OCR fallback, or see backend\requirements-ocr.txt.
    echo.
) else (
    echo Using the GPU Python environment: %API_PYTHON%
)

rem ---- 2. backend packages: install only when something is missing or broken -------------------
"%API_PYTHON%" -c "import fastapi, uvicorn, sqlalchemy, aiosqlite, pymupdf, PIL" >nul 2>nul
if errorlevel 1 (
    echo Installing / repairing backend packages ...
    "%API_PYTHON%" -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo Backend dependency installation failed.
        pause
        exit /b 1
    )
    "%API_PYTHON%" -c "import pymupdf" >nul 2>nul
    if errorlevel 1 "%API_PYTHON%" -m pip install --force-reinstall --no-deps PyMuPDF
)
if "%GPU_ENV%"=="1" (
    "%API_PYTHON%" -c "import transformers, accelerate, qwen_vl_utils" >nul 2>nul
    if errorlevel 1 echo WARNING: Qwen packages are missing. Install them with: "%API_PYTHON%" -m pip install -r backend\requirements-ocr.txt
)

rem ---- 3. frontend packages ----------------------------------------------------------------------
if not exist "node_modules\vite" goto :npm_install
if not exist "node_modules\katex" goto :npm_install
goto :npm_done
:npm_install
echo Installing frontend packages ...
call npm install
if errorlevel 1 (
    echo Frontend dependency installation failed.
    pause
    exit /b 1
)
:npm_done

rem ---- 4. free ports 8000 / 3000 if an older copy is still running ------------------------------
powershell -NoProfile -Command "foreach($p in 8000,3000){ Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('Stopping old process on port ' + $p + ' (pid ' + $_.OwningProcess + ')'); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"

rem ---- 5. start the servers ----------------------------------------------------------------------
set "RELOAD_FLAG="
if "%DEV_RELOAD%"=="1" set "RELOAD_FLAG=--reload"
set "PYTHONUNBUFFERED=1"
start "LumenEIOS Backend (API + Qwen)" cmd /k ""%API_PYTHON%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 %RELOAD_FLAG%"
start "LumenEIOS Frontend" cmd /k "cd /d ""%CD%"" && npm run dev -- --host 127.0.0.1 --port 3000"

rem ---- 6. load / check the models in their own window --------------------------------------------
if not "%NO_WARM%"=="1" (
    start "LumenEIOS models" cmd /k ""%API_PYTHON%" scripts\warm_models.py"
)

echo.
echo Frontend: http://localhost:3000
echo API docs: http://localhost:8000/api/v1/docs
echo Models:   watch the "LumenEIOS models" window (Qwen loads onto the GPU, about 1-2 minutes).
if not "%NO_BROWSER%"=="1" (
    timeout /t 8 >nul
    start "" http://localhost:3000
)
