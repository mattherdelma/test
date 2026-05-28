@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ===================================
echo  道路交通事故统计与可视化分析系统
echo ===================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.9+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

if not exist "static\js\echarts.min.js" (
    echo [首次运行] 正在下载前端依赖 ECharts...
    python download_libs.py
    if errorlevel 1 (
        echo [错误] 下载失败，请确认网络后重试
        pause
        exit /b 1
    )
)

if not exist ".deps_installed" (
    echo [首次运行] 正在安装 Python 依赖...
    python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [错误] 依赖安装失败
        pause
        exit /b 1
    )
    type nul > .deps_installed
)

if not exist "data\accidents.db" (
    echo [首次运行] 正在初始化数据库与演示数据...
    python seed_data.py
)

echo.
echo 启动中，浏览器将自动打开...
echo 默认账号: admin / admin123  (管理员)
echo          recorder / 123456 (录入员)
echo          viewer / 123456   (查看者)
echo.
echo 关闭此窗口将停止服务
echo.
python app.py

pause
