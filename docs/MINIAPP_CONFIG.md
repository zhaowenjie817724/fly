# 微信小程序 - PC端测试配置

## 快速开始

### 1. 安装微信开发者工具

下载：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

### 2. 配置后端地址

编辑小程序文件：`miniapp/pages/control/control.js`

**第14-17行**（onLoad函数）：

```javascript
onLoad() {
    // 改这两行为你的PC端地址
    const httpBase = wx.getStorageSync('httpBase') || 'http://127.0.0.1:8000';
    const wsUrl = wx.getStorageSync('wsUrl') || 'ws://127.0.0.1:8000/ws';
    this.setData({ httpBase, wsUrl });
    this.connectWs();
    this.loadFsmState();
},
```

### 3. 打开项目

1. 打开微信开发者工具
2. 选择 "导入项目"
3. 项目路径：`D:\wurenji\fly\miniapp`
4. AppID：可随意填写（开发版本）
5. 点击 "导入"

### 4. 运行小程序

1. 开发者工具右上角 "预览" 或 "真机预览"
2. 在模拟器中点击 "控制" 页面
3. 观察WebSocket连接状态（顶部绿色✓表示已连接）

---

## 小程序文件结构

```
miniapp/
├── app.js                      # 应用入口
├── app.json                    # 全局配置
├── pages/
│   ├── index/                  # 首页（默认）
│   ├── control/                # 飞行控制页面 ⭐ 主控制页
│   ├── events/                 # 事件列表页面
│   ├── event-detail/           # 事件详情页面
│   └── settings/               # 设置页面
└── sitemap.json                # 索引配置
```

---

## 各页面功能说明

### control.js - 飞行控制（主控制页）

**主要功能：**
- 实时显示飞行器姿态（Roll, Pitch, Yaw）
- 偏航控制（-30°, -10°, +10°, +30°）
- 飞行模式切换（悬停、引导、返航、降落）
- 紧急停止（长按确认）
- 命令日志（记录最近10条命令）

**关键代码片段：**

```javascript
// WebSocket连接和实时遥测接收
connectWs() {
    const { wsUrl } = this.data;
    wx.connectSocket({ url: wsUrl });

    wx.onSocketMessage((msg) => {
        const data = JSON.parse(msg.data);
        if (data.type === 'telemetry') {
            // 更新Roll, Pitch, Yaw等姿态数据
            const att = data.payload.attitude || {};
            this.setData({
                roll: (att.roll_deg || 0).toFixed(1),
                pitch: (att.pitch_deg || 0).toFixed(1),
                yaw: (att.yaw_deg || 0).toFixed(1)
            });
        }
    });
}

// 发送控制命令
sendCommand(cmd, params = {}) {
    const { httpBase } = this.data;
    wx.request({
        url: `${httpBase}/api/control/yaw`,  // 根据cmd类型改变endpoint
        method: 'POST',
        data: params,
        success: (res) => {
            // 处理响应
        }
    });
}
```

### events.js - 事件列表

**主要功能：**
- 显示后端产生的所有事件（检测、警告、模式切换等）
- 点击事件可查看详情
- 实时刷新

### event-detail.js - 事件详情

**主要功能：**
- 显示单个事件的完整信息
- 如果有图片快照，显示缩略图
- 事件时间、类型、置信度等详情

### settings.js - 设置页面

**主要功能：**
- 配置后端HTTP地址
- 配置WebSocket地址
- 保存到本地存储（wx.setStorage）

**配置示例：**

```javascript
// settings.js中的保存函数
saveSettings() {
    const { httpBase, wsUrl } = this.data;

    wx.setStorage({
        key: 'httpBase',
        data: httpBase,
        success: () => {
            wx.showToast({ title: '保存成功', icon: 'success' });
            // 刷新所有页面的连接
            // ...
        }
    });
}
```

---

## PC本地测试配置

### 场景1：本地SITL + 微信开发者工具模拟器

**配置：**
```javascript
const httpBase = 'http://127.0.0.1:8000';
const wsUrl = 'ws://127.0.0.1:8000/ws';
```

**条件：**
- 开发者工具运行在同一台PC
- FastAPI运行在 localhost:8000

**测试步骤：**
1. 启动SITL
2. 启动FastAPI后端
3. 打开微信开发者工具，导入miniapp项目
4. 在模拟器中打开"控制"页面
5. 观察WebSocket连接状态和数据流

### 场景2：本地SITL + 真机测试

**配置：**
```javascript
// 假设PC IP为 192.168.1.100
const httpBase = 'http://192.168.1.100:8000';
const wsUrl = 'ws://192.168.1.100:8000/ws';
```

**条件：**
- 手机/平板与PC在同一局域网
- PC防火墙允许8000端口（HTTP/WS）
- 小程序已配置服务器域名（如果发布）

**测试步骤：**
1. 启动SITL
2. 启动FastAPI后端
3. 在微信开发者工具中点击 "真机预览"
4. 用手机微信扫码
5. 在小程序中修改设置，填入 `http://192.168.1.100:8000`
6. 返回控制页面，观察连接状态

---

## 网络调试

### 1. 检查WebSocket连接

在开发者工具的"Console"标签中查看：

```javascript
// 这会在每个消息到达时打印日志
wx.onSocketMessage((msg) => {
    console.log('WebSocket消息:', msg.data);
    // ...
});
```

### 2. 检查HTTP请求

开发者工具 → 工具 → Network，查看所有HTTP请求：
- GET `/api/fsm` - 获取FSM状态
- POST `/api/control/yaw` - 发送偏航命令
- POST `/api/control/mode` - 发送模式切换命令
- POST `/api/control/estop` - 发送紧急停止命令

### 3. 实时日志

开发者工具 → 工具 → 实时日志：
- 查看小程序运行时的错误和警告
- 查看网络请求的返回状态

---

## 常见问题

### Q1: "未连接" 一直显示红色

**可能原因：**
1. FastAPI未启动
2. 地址配置错误
3. 防火墙阻止了8000端口

**解决方案：**
```bash
# 验证FastAPI是否运行
curl http://127.0.0.1:8000/health

# 查看Windows防火墙状态
netstat -ano | findstr "8000"

# 如果防火墙阻止，在PowerShell中运行
New-NetFirewallRule -DisplayName "FastAPI" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
```

### Q2: 命令发送失败（✗图标）

**可能原因：**
1. 后端未连接到SITL
2. 命令格式不对
3. 速率限制

**解决方案：**
```bash
# 检查FastAPI日志输出
# 查看是否有错误消息

# 在前端检查命令参数格式
# 例如：yaw_deg应该是数字，不是字符串
```

### Q3: 遥测数据不更新

**可能原因：**
1. WebSocket连接已建立但收不到数据
2. SITL未输出到14551端口
3. FastAPI telemetry模式未配置为mavlink_udp

**解决方案：**
```bash
# 检查dev.yaml
cat configs/dev.yaml | grep -A5 telemetry

# 应该看到：
# telemetry:
#   enabled: true
#   mode: mavlink_udp
#   mavlink:
#     udp: "udp:127.0.0.1:14551"

# 如果是mock，手动改为mavlink_udp
```

### Q4: 小程序模拟器显示"服务器配置错误"

**可能原因：**
1. 地址格式错误（如少了http://前缀）
2. IP地址输入错误
3. 端口号错误

**解决方案：**
```javascript
// 确保格式正确
const httpBase = 'http://127.0.0.1:8000';  // 正确
const wsUrl = 'ws://127.0.0.1:8000/ws';    // 正确

// 避免这些格式
const httpBase = '127.0.0.1:8000';         // ❌ 缺少http://
const wsUrl = 'http://127.0.0.1:8000/ws';  // ❌ ws应该用ws:// 或 wss://
```

---

## 性能优化（树莓派部署时）

小程序目前的特点：
- 每1秒刷新一次遥测数据
- 命令发送无延迟限制（FastAPI端有速率限制5Hz）
- 事件实时推送（通过WebSocket）

对于树莓派2GB环境，建议：
1. 减少WebSocket更新频率（改为2秒一次）
2. 减少实时事件流数量（保留最近50条而非所有）
3. 使用CDN加速静态资源

---

## 小程序特殊功能

### 紧急停止（双重确认）

```javascript
onEstopLongPress() {
    // 1. 长按触发振动反馈
    wx.vibrateShort({ type: 'heavy' });

    // 2. 弹出确认对话框
    wx.showModal({
        title: '确认急停',
        content: '将立即停止所有运动并切换到悬停模式',
        confirmText: '确认急停',
        confirmColor: '#ef4444',  // 红色
        success: (res) => {
            if (res.confirm) {
                // 3. 发送STOP命令
                this.executeEstop();
            }
        }
    });
}
```

这样确保用户不会误触紧急停止。

### 命令日志

最多显示最近10条命令，包括：
- 命令时间戳
- 命令类型和参数
- 执行结果（✓成功，✗失败）

```javascript
addLog(time, cmd, success) {
    const logs = [{ time, cmd, success }].concat(this.data.cmdLogs).slice(0, 10);
    this.setData({ cmdLogs: logs });
}
```

---

## 后续改进建议

1. **离线模式**：缓存命令，待网络恢复后同步
2. **命令队列**：支持批量命令预设和自动执行
3. **性能指标**：显示帧率、延迟、丢包率等网络指标
4. **语音反馈**：命令成功/失败时播放不同提示音
5. **地理位置**：集成高德地图，显示无人机实时位置

