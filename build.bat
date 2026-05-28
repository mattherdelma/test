@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================
echo  打包为单文件 EXE
echo ===================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python
    pause
    exit /b 1
)

python -m pip install --quiet -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python build_exe.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo 打包完成。可执行文件位于 dist\ 目录。
echo 双击 dist\*.exe 即可使用，无需 Python 环境。
echo.
pause
