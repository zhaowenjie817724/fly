# SITL 联调指南（PC端验证）

本文档指导如何在PC端使用ArduPilot SITL模拟器验证通感之眼2.0的控制闭环。

## 一、环境准备

### 1.1 安装ArduPilot SITL（Windows）

**方法A：WSL2（推荐）**
```bash
# 在WSL2 Ubuntu中
git clone https://github.com/ArduPilot/ardupilot.git
cd ardupilot
git submodule update --init --recursive
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile
```

**方法B：Mission Planner内置SITL**
1. 打开Mission Planner
2. 菜单：SIMULATION → 选择机型（Copter）
3. 自动启动SITL并连接

### 1.2 端口规划

| 端口 | 用途 | 连接方 |
|-----|------|-------|
| UDP 14550 | Mission Planner | 地面站遥测/参数 |
| UDP 14551 | 伴侣机程序 | FSM/控制指令 |
| TCP 5760 | SITL默认 | 可选备用 |

### 1.3 mavlink-router配置（可选）

如需多端口复用，创建`/etc/mavlink-router/main.conf`：
```ini
[General]
TcpServerPort=5760

[UdpEndpoint mp]
Mode = Normal
Address = 127.0.0.1
Port = 14550

[UdpEndpoint companion]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

## 二、启动流程

### 2.1 启动SITL

**WSL2方式**
```bash
cd ~/ardupilot/ArduCopter
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551 --map --console
```

**Mission Planner方式**
1. SIMULATION → Multirotor → Copter
2. 等待"Got HEARTBEAT"提示

### 2.2 启动后端服务

```bash
cd D:\wurenji\fly
.\.venv\Scripts\activate
python apps/service/server.py --config configs/service.yaml --run latest
```

### 2.3 验证MAVLink连通

```bash
# 测试心跳
python -c "
from pymavlink import mavutil
m = mavutil.mavlink_connection('udp:127.0.0.1:14551')
hb = m.wait_heartbeat(timeout=10)
print('HEARTBEAT:', hb)
"
```

## 三、控制闭环验证

### 3.1 偏航控制测试

```bash
# 方法1：通过API
curl -X POST http://127.0.0.1:8000/api/control/yaw \
  -H "Content-Type: application/json" \
  -d '{"yaw_deg": 45, "yaw_rate_deg_s": 30}'

# 方法2：通过小程序控制面板
# 打开小程序 → 控制 → 点击左转/右转按钮
```

**验证点**：
- Mission Planner地图上飞机航向变化
- `runs/latest/commands.jsonl`有记录
- 后端日志显示指令发送成功

### 3.2 模式切换测试

```bash
curl -X POST http://127.0.0.1:8000/api/control/mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "LOITER"}'
```

**验证点**：
- Mission Planner显示模式变为LOITER
- 后端返回`{"accepted": true}`

### 3.3 急停测试

```bash
curl -X POST http://127.0.0.1:8000/api/control/estop
```

**验证点**：
- 飞机切换到LOITER/HOLD模式
- 停止当前运动

## 四、FSM回放验证

### 4.1 生成测试数据

```bash
# 1. 运行采集（使用Mock模式）
python apps/acquisition/run_acq.py --config configs/dev.yaml --duration 60

# 2. 运行YOLO推理
python apps/vision/yolo_infer.py --config configs/vision.yaml --run latest

# 3. 运行DOA
python apps/audio/doa_offline.py --config configs/doa.yaml --run latest

# 4. 融合
python apps/fusion/fuse_replay.py --run latest
```

### 4.2 FSM回放（Dry-Run）

```bash
# 不发送真实MAVLink指令
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest --dry-run
```

### 4.3 FSM回放（真实控制）

```bash
# 确保SITL已启动且UDP 14551可达
python apps/control/fsm_runner.py --config configs/fsm.yaml --run latest --speed 1.0
```

**观察**：
- Mission Planner上飞机响应yaw指令
- `runs/latest/commands.jsonl`记录所有指令
- `runs/latest/events.jsonl`记录状态转换

## 五、小程序联调

### 5.1 配置服务器地址

1. 打开微信开发者工具
2. 进入"设置"页面
3. 输入HTTP地址：`http://<PC内网IP>:8000`
4. 输入WS地址：`ws://<PC内网IP>:8000/ws`
5. 点击"测试连接"

### 5.2 功能验证清单

| 功能 | 验证步骤 | 预期结果 |
|-----|---------|---------|
| 仪表盘 | 打开首页 | 显示遥测数据、连接状态 |
| 事件列表 | 打开事件页 | 显示历史事件、支持筛选 |
| 事件详情 | 点击事件 | 显示详情、快照图片 |
| 偏航控制 | 控制页点击左转 | SITL飞机转向、命令记录 |
| 急停 | 长按急停按钮 | 飞机切换LOITER |

## 六、常见问题

### Q1：无法连接SITL

**检查**：
1. SITL是否已启动（看到"APM: EKF2 IMU0 is using GPS"）
2. UDP端口是否正确（14551）
3. 防火墙是否放行

```bash
# Windows防火墙放行
netsh advfirewall firewall add rule name="SITL UDP" dir=in action=allow protocol=UDP localport=14550-14560
```

### Q2：Mission Planner无法同时连接

**解决**：使用mavlink-router或SITL多输出：
```bash
sim_vehicle.py --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
```

### Q3：小程序WebSocket断连

**检查**：
1. 是否在开发者工具中关闭了"不校验合法域名"
2. 服务器CORS是否已启用
3. 网络是否在同一局域网

### Q4：控制指令被拒绝（rate_limited）

**原因**：指令频率超过5Hz限制

**解决**：等待200ms后重试，或调整`configs/service.yaml`中的`command_rate_limit_hz`

## 七、联调检查清单

- [ ] SITL启动并输出心跳
- [ ] Mission Planner连接成功（UDP 14550）
- [ ] 后端服务启动（8000端口）
- [ ] pymavlink心跳测试通过（UDP 14551）
- [ ] API偏航控制测试通过
- [ ] 小程序WebSocket连接成功
- [ ] 小程序控制功能正常
- [ ] FSM回放验证通过

## 八、下一步

完成PC端SITL联调后，可进行：
1. 真机MAVLink串口连接测试
2. 树莓派部署与验证
3. 室外飞行测试
