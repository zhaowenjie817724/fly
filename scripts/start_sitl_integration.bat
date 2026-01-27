@echo off
REM Mission Planner / SITL 联调脚本
REM 启动所有必要服务进行联调测试

echo ============================================================
echo Mission Planner / SITL 联调脚本
echo ============================================================

set REPO_ROOT=%~dp0..
cd /d %REPO_ROOT%

REM 激活虚拟环境
call .venv\Scripts\activate.bat

echo.
echo [1/4] 检查MAVLink连接...
python tools\test_mavlink_connection.py --udp udp:127.0.0.1:14551 --api http://127.0.0.1:8000

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo 连接测试失败！请确保：
    echo 1. Mission Planner SITL 已启动
    echo 2. 端口 14551 可用
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo [2/4] 启动遥测接收器...
start "MAVLink Receiver" cmd /k "cd /d %REPO_ROOT% && .venv\Scripts\activate && python apps\acquisition\mavlink_receiver.py --udp udp:127.0.0.1:14551 --run latest"

echo.
echo [3/4] 启动后端服务...
start "Backend Service" cmd /k "cd /d %REPO_ROOT% && .venv\Scripts\activate && python apps\service\server.py --config configs\service.yaml --run latest"

echo.
echo [4/4] 等待服务启动...
timeout /t 5 /nobreak > nul

echo.
echo ============================================================
echo 联调环境已启动！
echo.
echo 服务地址：
echo   - REST API:   http://127.0.0.1:8000
echo   - WebSocket:  ws://127.0.0.1:8000/ws
echo   - 健康检查:   http://127.0.0.1:8000/health
echo.
echo 测试命令：
echo   curl -X POST http://127.0.0.1:8000/api/control/yaw -H "Content-Type: application/json" -d "{\"yaw_deg\": 30}"
echo.
echo 观察Mission Planner地图上飞机航向是否变化
echo ============================================================
pause
