@echo off
chcp 65001 >nul
title LandState GCS + fly 系统启动器

echo ============================================
echo   LandState GCS + fly 集成系统启动器
echo ============================================
echo.

:: 检查是否有 SITL 环境
where sim_vehicle.py >nul 2>&1
if %errorlevel%==0 (
    echo [√] 检测到 ArduPilot SITL 环境
    set HAS_SITL=1
) else (
    echo [!] 未检测到 SITL，将使用模拟数据模式
    set HAS_SITL=0
)

echo.
echo 请选择启动模式：
echo   1. SITL 模拟 (需要安装 ArduPilot SITL)
echo   2. 仅启动 LandState GCS (手动连接真机/其他模拟器)
echo   3. Mock 模式 (fly 使用模拟数据)
echo.
set /p MODE="请输入选项 (1/2/3): "

if "%MODE%"=="1" goto SITL_MODE
if "%MODE%"=="2" goto GCS_ONLY
if "%MODE%"=="3" goto MOCK_MODE
goto END

:SITL_MODE
echo.
echo [1/3] 启动 ArduPilot SITL...
echo       输出端口: 14550 (LandState GCS), 14551 (fly)
start "ArduPilot SITL" cmd /k "sim_vehicle.py -v ArduCopter --console --map --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551"
timeout /t 10 /nobreak >nul

echo [2/3] 启动 LandState GCS...
start "LandState GCS" "D:\landstate\dist\LandStateGCS.exe"
timeout /t 3 /nobreak >nul

echo [3/3] 启动 fly 伴侣机系统...
cd /d D:\wurenji\fly
start "fly System" cmd /k "python -m apps.acquisition.run_acq --config configs/pc_landstate.yaml"

echo.
echo ============================================
echo   系统已启动！
echo   - SITL 模拟器运行中
echo   - LandState GCS: UDP Listen 14550
echo   - fly 系统: 连接 14551
echo ============================================
goto END

:GCS_ONLY
echo.
echo 启动 LandState GCS...
start "LandState GCS" "D:\landstate\dist\LandStateGCS.exe"
echo.
echo LandState GCS 已启动，请手动配置连接参数。
goto END

:MOCK_MODE
echo.
echo [1/2] 启动 LandState GCS (模拟器模式)...
start "LandState GCS" "D:\landstate\dist\LandStateGCS.exe"
timeout /t 2 /nobreak >nul

echo [2/2] 启动 fly 系统 (Mock 模式)...
cd /d D:\wurenji\fly
start "fly System" cmd /k "python -m apps.acquisition.run_acq --config configs/pc_smoke.yaml"

echo.
echo ============================================
echo   Mock 模式已启动！
echo   - LandState GCS: 可启用内置模拟器
echo   - fly 系统: 使用模拟数据
echo ============================================
goto END

:END
echo.
pause
