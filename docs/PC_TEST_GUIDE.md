# 通感之眼2.0 - PC端完整测试指南

## 整体架构

```
[ArduPilot SITL] --UDP 14550,14551,14552--> [FastAPI后端]
                                                    ↓
                                          (读取MAVLink数据)
                                                    ↓
                                  ┌─────────────────┼─────────────────┐
                                  ↓                 ↓                 ↓
                            [前端浏览器]     [小程序调试]      [Mission Planner]
                            (http://localhost:8000/web/control.html)
```

本测试环境完全运行在PC端，无需树莓派或实物无人机，使用SITL模拟器。

---

## 第一步：准备环境

### 1.1 安装ArduPilot SITL

#### 方式A：系统安装（推荐有Linux/WSL环境）
```bash
# 克隆ArduPilot仓库
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot

# 安装依赖（Ubuntu/Debian）
Tools/environment_install/install-prereqs-ubuntu.sh -y

# 编译
./waf configure --board sitl
./waf copter

# 添加到PATH
export PATH=$PATH:/path/to/ardupilot/tools/autotest
```

#### 方式B：Docker运行（推荐，最简单）
```bash
# 安装Docker: https://www.docker.com/products/docker-desktop

# 运行SITL容器（会自动启动SITL并输出UDP数据到14550,14551,14552）
docker run -it --rm \
  -p 14550:14550/udp \
  -p 14551:14551/udp \
  -p 14552:14552/udp \
  ardupilot/ardupilot:latest \
  sim_vehicle.py -v ArduCopter --no-rebuild \
    --out=udp:0.0.0.0:14550 \
    --out=udp:0.0.0.0:14551 \
    --out=udp:0.0.0.0:14552
```

### 1.2 安装Python依赖

```bash
cd D:\wurenji\fly

# 安装FastAPI和相关依赖
pip install fastapi uvicorn pymavlink pyyaml pydantic

# 或使用requirements文件
pip install -r requirements-pi.txt
```

---

## 第二步：启动SITL模拟器

### 2.1 使用Command Line启动（推荐）

#### Windows (如已安装ArduPilot)：
```bash
# 打开PowerShell或CMD
# 找到ArduPilot安装目录，运行：
sim_vehicle.py -v ArduCopter ^
  --out=udp:127.0.0.1:14550 ^
  --out=udp:127.0.0.1:14551 ^
  --out=udp:127.0.0.1:14552

# 或者直接使用Docker（更简单）
docker run -it --rm ^
  -p 14550:14550/udp ^
  -p 14551:14551/udp ^
  -p 14552:14552/udp ^
  ardupilot/ardupilot:latest ^
  sim_vehicle.py -v ArduCopter --no-rebuild ^
    --out=udp:0.0.0.0:14550 ^
    --out=udp:0.0.0.0:14551 ^
    --out=udp:0.0.0.0:14552
```

期望输出：
```
Ready to FLY ArduCopter
SITL started successfully
MAVProxy started successfully
Sending MAVLink data to UDP 127.0.0.1:14550, 14551, 14552
```

> **验证**: 在另一个CMD窗口运行 `netstat -ano | findstr "14550"` 确保SITL正在监听

---

## 第三步：启动FastAPI后端

打开新的PowerShell/CMD窗口：

```bash
cd D:\wurenji\fly

# 启动FastAPI服务（使用dev.yaml配置，连接SITL的14551端口）
python apps/service/server.py --config configs/dev.yaml --port 8000
```

期望输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

此时FastAPI已启动并等待：
- WebSocket客户端连接到 `ws://127.0.0.1:8000/ws`
- REST API调用到 `http://127.0.0.1:8000/api/*`
- 前端页面访问 `http://127.0.0.1:8000/web/control.html`

### 3.1 验证后端健康状态

```bash
# 在第三个CMD窗口执行
curl http://127.0.0.1:8000/health

# 期望返回
{
  "status": "ok",
  "warnings": [],
  "telemetry": {
    "link_status": "OK",
    "age_sec": 0.123
  },
  "system": { ... }
}
```

---

## 第四步：PC浏览器前端测试（推荐首先测试）

### 4.1 打开前端控制面板

在**任何现代浏览器**（Chrome, Firefox, Edge）中打开：

```
http://127.0.0.1:8000/web/control.html
```

### 4.2 前端界面说明

| 区域 | 功能 |
|------|------|
| **系统状态** | 实时显示WebSocket连接状态、飞行器姿态角度、高度、速度 |
| **后端地址** | 可自定义（默认127.0.0.1:8000），用于多机测试 |
| **无人机控制** | 偏航控制、飞行模式切换、紧急停止 |
| **命令日志** | 显示已发送命令和执行结果 |
| **实时事件** | 显示后端产生的事件（检测、模式切换等） |

### 4.3 测试步骤

1. **验证连接**：页面加载后，"系统状态"应显示 ✓ 已连接（绿色点）
   - 如显示 ✗ 已断开，检查SITL和FastAPI是否运行

2. **查看遥测数据**：
   - 观察 Yaw, Roll, Pitch 数值是否实时更新
   - 观察高度、速度是否有变化

3. **发送控制命令**：
   - 点击 "左转 -30°"，检查命令日志是否显示✓
   - 点击 "悬停"，检查飞行模式是否更新
   - 点击 "紧急停止"，确认警告对话框出现

4. **监听事件流**：
   - 实时事件区应该显示后端产生的事件日志

### 4.4 前端调试技巧

- 打开浏览器开发者工具（F12）→ Console，查看WebSocket消息
- 修改后端地址可以测试不同端口的服务
- 命令日志可帮助诊断通信问题

---

## 第五步：API测试（可选，用curl或Postman）

### 5.1 获取遥测数据

```bash
curl http://127.0.0.1:8000/api/telemetry
```

返回最新的MAVLink遥测信息（JSON格式）

### 5.2 获取事件列表

```bash
curl "http://127.0.0.1:8000/api/events?limit=10"
```

返回最近10条事件

### 5.3 发送控制命令

```bash
# 左转30°
curl -X POST http://127.0.0.1:8000/api/control/yaw \
  -H "Content-Type: application/json" \
  -d '{"yaw_deg": -30}'

# 切换到悬停模式
curl -X POST http://127.0.0.1:8000/api/control/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "LOITER"}'

# 紧急停止
curl -X POST http://127.0.0.1:8000/api/control/estop
```

### 5.4 WebSocket推送订阅

```bash
# 使用wscat工具（npm install -g wscat）
wscat -c ws://127.0.0.1:8000/ws

# 然后在浏览器前端发送命令，观察WebSocket消息推送
```

---

## 第六步：Mission Planner集成测试（可选）

### 6.1 安装Mission Planner

下载并安装：https://ardupilot.org/planner/docs/mission-planner-installation.html

### 6.2 连接Mission Planner到SITL

1. 打开Mission Planner
2. 点击 **Connect** 按钮
3. 选择 **UDP**
4. 输入 `127.0.0.1:14550`
5. 点击 **Connect**

### 6.3 验证多端点

- Mission Planner应显示实时遥测数据（来自14550端口）
- 同时，浏览器前端应实时更新（来自14551端口）
- 命令从两端都可以发送

---

## 第七步：微信小程序测试（需要微信开发者工具）

### 7.1 配置小程序后端地址

编辑 `miniapp/pages/control/control.js`，第15-16行：

```javascript
const httpBase = wx.getStorageSync('httpBase') || 'http://127.0.0.1:8000';  // 改为你的PC IP
const wsUrl = wx.getStorageSync('wsUrl') || 'ws://127.0.0.1:8000/ws';      // 如在局域网测试
```

### 7.2 在微信开发者工具中测试

1. 打开微信开发者工具
2. 导入项目 `D:\wurenji\fly\miniapp`
3. 在模拟器中进入"控制"页面
4. 观察WebSocket连接状态和遥测数据实时更新
5. 发送命令（偏航、模式切换）

### 7.3 网络调试

- 开发者工具 → 工具 → 实时日志，查看网络请求和错误
- 确保小程序可以访问后端（可能需要配置CORS，已在server.py中启用）

---

## 第八步：完整端到端测试流程

### 8.1 启动顺序（重要！）

```
1. 启动SITL (docker或 sim_vehicle.py)
   ↓
2. 启动FastAPI后端 (python apps/service/server.py)
   ↓
3. 打开前端页面 (浏览器打开 http://127.0.0.1:8000/web/control.html)
   ↓
4. （可选）打开Mission Planner
   ↓
5. （可选）打开微信小程序调试
```

### 8.2 测试场景

**场景1：前端到SITL的遥测链路**
- ✓ 前端页面显示"已连接"
- ✓ 实时更新Roll, Pitch, Yaw数值
- ✓ 高度、速度数值随时间变化

**场景2：前端到SITL的控制链路**
- ✓ 点击"左转-30°"，命令日志显示✓
- ✓ SITL收到命令（在SITL窗口可看到消息）
- ✓ 飞行器Yaw角度变化

**场景3：多端点并行**
- ✓ Mission Planner + 浏览器前端 + 小程序 同时连接
- ✓ 从任一端点发送命令，其他端点实时显示效果

**场景4：异常处理**
- ✓ 断开SITL，前端显示"已断开"，3秒后自动重连
- ✓ 发送无效命令，命令日志显示✗失败

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 前端显示"已断开" | FastAPI未启动或WebSocket配置错误 | 检查FastAPI是否运行，确认地址正确 |
| "连接超时" | SITL未启动或端口被占用 | 运行SITL，检查14550-14552端口 |
| 命令发送失败 | FastAPI未收到SITL数据 | 检查dev.yaml中telemetry.mode是否为mavlink_udp |
| 小程序无法连接 | 跨域问题或地址错误 | CORS已启用，检查httpBase是否正确 |
| "索引超出范围" | 脚本中数组访问越界 | 见下面"调试索引错误"章节 |

---

## 调试索引错误

如果遇到"索引超出范围，必须是非负数的集合"错误：

### 可能的位置：

1. **小程序control.js:104** （命令日志数组）
   ```javascript
   const logs = [{ time, cmd, success }].concat(this.data.cmdLogs).slice(0, 10);
   ```

2. **FastAPI server.py:188** （JSONL分页）
   ```python
   return records[offset:offset + limit]  # Python中offset可能超出范围
   ```

3. **前端control.html** （事件流数组操作）
   ```javascript
   stream.children[0]?.textContent  // 安全操作
   ```

### 常见原因：
- cmdLogs未初始化为空数组
- offset参数为负数
- 试图访问不存在的数组索引

### 调试步骤：
1. 打开浏览器开发者工具（F12）
2. 进入 **Console** 标签，查看具体错误行号
3. 或查看FastAPI日志输出（包含Python错误堆栈）
4. 根据错误行号在对应文件中修复

---

## 总结

你现在有一个完整的PC端测试环境：

- ✓ SITL模拟器 → MAVLink数据源
- ✓ FastAPI后端 → WebSocket + REST API
- ✓ 前端web页面 → 实时控制和监控
- ✓ 小程序 → 完整功能测试（可选）
- ✓ Mission Planner集成 → 专业级地面站对接

**后续可直接在树莓派上部署**，无需改动代码，只需改配置文件（configs/pi_2gb_final.yaml）和更改MAVLink来源为实际飞控。

