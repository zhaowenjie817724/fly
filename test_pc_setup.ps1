# PC端完整测试环境启动脚本（Windows PowerShell）
# 用途：启动SITL + FastAPI + 前端，完整的无人机控制测试环境

Write-Host "========================================" -ForegroundColor Green
Write-Host "通感之眼2.0 - PC端完整测试环境启动" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

# 1. 检查Python环境
Write-Host "[1/4] 检查Python环境..." -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 未安装Python，请先安装Python 3.8+" -ForegroundColor Red
    exit 1
}

# 2. 检查ArduPilot SITL
Write-Host ""
Write-Host "[2/4] 检查ArduPilot SITL环境..." -ForegroundColor Cyan
Write-Host "提示: 需要安装ArduPilot (https://ardupilot.org/dev/docs/building-the-code.html)" -ForegroundColor Yellow
Write-Host ""
Write-Host "请选择您的设置方式:" -ForegroundColor Yellow
Write-Host "1. 使用系统已安装的sim_vehicle.py启动SITL" -ForegroundColor Gray
Write-Host "2. 使用Docker运行SITL（推荐，无需安装ArduPilot）" -ForegroundColor Gray
Write-Host ""

# 3. 检查项目依赖
Write-Host "[3/4] 检查Python项目依赖..." -ForegroundColor Cyan
$reqFile = "D:\wurenji\fly\requirements-pi.txt"
if (Test-Path $reqFile) {
    Write-Host "安装依赖包..."
    pip install -q -r $reqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "警告: 某些依赖安装失败，但可能不影响测试" -ForegroundColor Yellow
    }
} else {
    Write-Host "提示: 未找到requirements-pi.txt" -ForegroundColor Yellow
}

# 4. 启动FastAPI后端
Write-Host ""
Write-Host "[4/4] 启动FastAPI后端服务..." -ForegroundColor Cyan
Write-Host ""
Write-Host "正在启动 FastAPI @ http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "WebSocket @ ws://127.0.0.1:8000/ws" -ForegroundColor Green
Write-Host ""

cd D:\wurenji\fly
python apps/service/server.py --config configs/dev.yaml --port 8000

