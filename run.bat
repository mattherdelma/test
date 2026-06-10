@echo off
REM ==========================================================
REM  Donghai Traffic Accident System - one click launcher
REM  (Pure ASCII + CRLF on purpose: avoids cmd.exe UTF-8/chcp
REM   line-splitting bug. The app UI in the browser is Chinese.)
REM ==========================================================
setlocal
cd /d "%~dp0"

REM --- locate python: try "python", then the "py" launcher ---
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Please install Python 3.9+ and
        echo         tick "Add Python to PATH" during installation.
        echo         Download: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PY=py"
)
echo [OK] Using interpreter: %PY%

REM --- first run: download front-end libs (ECharts + Leaflet) ---
if not exist "static\js\echarts.min.js" (
    echo [SETUP] Downloading front-end libraries ...
    %PY% download_libs.py
    if errorlevel 1 (
        echo [ERROR] Download failed. Check your network and retry.
        pause
        exit /b 1
    )
)
if not exist "static\js\leaflet.js" (
    echo [SETUP] Downloading map engine Leaflet ...
    %PY% download_libs.py
)

REM --- first run: fetch Donghai map data (boundary + roads) ---
REM     needs internet; skipped if present; failure does NOT block start
if not exist "static\js\maps\donghai_roads.json" (
    echo [SETUP] Fetching Donghai county map data ...
    %PY% download_donghai_map.py
)

REM --- first run: install python deps ---
if not exist ".deps_installed" (
    echo [SETUP] Installing Python dependencies ...
    %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
    type nul > .deps_installed
)

REM --- first run: init database + demo data ---
if not exist "data\accidents.db" (
    echo [SETUP] Initializing database and demo data ...
    %PY% seed_data.py
)

echo.
echo Starting server, the browser will open automatically...
echo URL : http://127.0.0.1:5000
echo User: admin / admin123     ^(administrator^)
echo       recorder / 123456    ^(recorder^)
echo       viewer / 123456      ^(viewer^)
echo.
echo Close this window to stop the service.
echo.
%PY% app.py

pause
endlocal
