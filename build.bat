@echo off
REM ==========================================================
REM  Build single-file EXE (pure ASCII + CRLF on purpose)
REM ==========================================================
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python not found. Install Python 3.9+ first.
        pause
        exit /b 1
    )
    set "PY=py"
)

echo [STEP] Installing dependencies ...
%PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [STEP] Building EXE ...
%PY% build_exe.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo Build finished. The EXE is in the dist\ folder.
echo Double click dist\*.exe to run, no Python needed.
echo.
pause
endlocal
