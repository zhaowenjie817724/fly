# Architecture & Interface Specification v0.1

## 1. Purpose（目的）

本文档冻结无人机软件系统 v0.1 的架构与接口合同，目的是在硬件与算法尚未完全就绪时，仍可并行推进开发与联调，并避免接口字段反复变动导致返工。

核心原则：
- 模块边界清晰：模块之间不得直接读写对方内部状态
- 消息合同优先：模块通信只能通过消息/接口完成
- 可降级：任一传感器/链路失败必须有明确的降级行为
- 可复现：日志与数据落盘格式必须支持回放

## 2. System Boundary（系统边界）

系统组成：
- Companion Computer（伴侣机）：运行本软件（如树莓派）
- Flight Controller（飞控）：通过 MAVLink 与伴侣机通信
- Sensors（传感器）：摄像头 / 麦阵 / 热像（可选）
- External Client（外部客户端）：上位机/小程序（Sprint 0 仅冻结接口，不实现 UI）

## 3. Module Map（模块划分）

| 模块 | 职责 | 输入 | 输出 | 频率/延迟目标 | 失败与降级行为 |
|---|---|---|---|---|---|
| TelemetryCapture | 读取飞控遥测 | MAVLink | TelemetryMsg | 1–10 Hz | 断链→重连；link_status=LOST；只读不控 |
| VideoCapture | 摄像头采集与落盘 | Camera | FrameMsg/VideoFile | 20–30 FPS | 降分辨率/跳帧；仍落盘 |
| AudioCapture | 麦阵采集与落盘 | MicArray | AudioChunk/File | 连续流 | 缺通道→DEGRADED；仍落盘 |
| Perception-Vision | 视觉检测（接口） | FrameMsg | ObservationMsg | ≤200 ms | 输出 INVALID 或不输出 |
| Perception-Audio | 音频方位（接口） | AudioChunk | ObservationMsg | ≤300 ms | 输出 INVALID 或不输出 |
| Fusion | 多源融合 | ObservationMsg* | FusedObservation | ≤200 ms | 缺源→退化融合；标记 DEGRADED |
| FSM/Decision | 状态机与决策 | Obs/Tel/Event | CommandMsg/EventMsg | ≤100 ms | Safety：HOLD/STOP |
| Control | 控制输出到飞控 | CommandMsg | MAVLink Cmd | ≤100 ms | 限幅/抑制；飞控丢链→禁止输出 |
| Service(API) | 对外接口 | 内部消息 | WS/HTTP | - | 无客户端→只落盘 |
| Storage/Logger | 统一落盘 | 全部消息 | JSONL/索引 | - | 写失败→告警事件 |

说明：
- “算法模块”在 v0.1 只冻结输入输出，不要求实现算法本体。
- “Storage/Logger”用于离线回放与联调定位，属于基础设施模块。

## 4. Dataflow（端到端数据流）

至少包含以下四条端到端链路：

1) 飞控遥测链路  
FlightController → TelemetryCapture → TelemetryMsg → Logger → (WS 推送)

2) 视觉链路  
Camera → VideoCapture → FrameMsg → Perception-Vision → ObservationMsg → Fusion → FSM/Decision → (Event/Command)

3) 音频链路  
MicArray → AudioCapture → AudioChunk → Perception-Audio → ObservationMsg → Fusion → FSM/Decision

4) 控制链路  
FSM/Decision → CommandMsg → Control → MAVLink → FlightController

## 5. Ports & Protocols（端口与协议口径）

### 5.1 MAVLink（飞控通信）
- 传输层：串口/USB 或 UDP（取决于硬件配置）
- v0.1 要求：能稳定获得 heartbeat 与基础遥测（字段可缺失，但必须有 link_status 与 time）

### 5.2 内部消息通信（模块间）
- v0.1 口径：抽象为 Pub/Sub 消息总线（实现可在后续 Sprint 决定）
- 原则：模块间不得以“直接函数调用读取对方内部状态”的方式耦合

### 5.3 对外接口（Service）
- v0.1：冻结字段与资源口径
  - WebSocket：推送 TelemetryMsg / ObservationMsg / EventMsg
  - HTTP：提供健康检查、版本号、运行状态、回放索引（仅冻结，不要求实现）

## 6. Message Spec v0.1（消息合同）

### 6.1 Common（所有消息通用字段）
所有消息必须包含：
- version: "0.1"
- time:
  - epoch_ms: int64（Unix 毫秒）
  - mono_ms: int64（单调时钟毫秒，用于回放与对齐）

### 6.2 ObservationMsg（统一观测）
字段定义：
- version: "0.1"
- time: { epoch_ms, mono_ms }
- source: "vision" | "audio" | "thermal" | "fusion"
- bearing_deg: float  
  - 坐标系冻结：**机体前向为 0°，顺时针为正**  
  - 取值范围建议：[0, 360)
- roi: object（视觉来源必填）
  - x, y, w, h: int（像素坐标）
  - frame_w, frame_h: int（用于解释 roi）
- confidence: float（0–1）
- status: "OK" | "DEGRADED" | "INVALID" | "NO_SIGNAL"
- extras: object（可选扩展：class、track_id 等）

示例：
```json
{
  "version": "0.1",
  "time": { "epoch_ms": 1768440000123, "mono_ms": 123456789 },
  "source": "vision",
  "bearing_deg": 32.5,
  "roi": { "x": 420, "y": 180, "w": 120, "h": 200, "frame_w": 1280, "frame_h": 720 },
  "confidence": 0.78,
  "status": "OK",
  "extras": { "class": "person", "track_id": 7 }
}
```

6.3 TelemetryMsg（遥测）

字段定义（v0.1 允许部分字段缺失，但必须包含 link_status 与 time）：

version: "0.1"

time: { epoch_ms, mono_ms }

link_status: "OK" | "DEGRADED" | "LOST"

battery（可选）:

voltage_v: float

remaining_pct: int

attitude（可选）:

roll_deg, pitch_deg, yaw_deg: float

gps（可选）:

lat, lon: float

alt_m: float

示例：

{
  "version": "0.1",
  "time": { "epoch_ms": 1768440000456, "mono_ms": 123457122 },
  "link_status": "OK",
  "battery": { "voltage_v": 15.3, "remaining_pct": 86 },
  "attitude": { "roll_deg": 0.8, "pitch_deg": -1.2, "yaw_deg": 90.0 }
}

6.4 CommandMsg（控制指令）

目的：冻结“允许发什么指令”和“安全边界”，避免控制侧越权。

字段定义：

version: "0.1"

time: { epoch_ms, mono_ms }

type: "HOLD" | "STOP" | "SET_YAW" | "SET_VELOCITY" | "ARM" | "DISARM"

params: object（随 type 不同而不同）

safety: object（限幅）

max_rate_deg_s?: float

max_speed_m_s?: float

示例：

{
  "version": "0.1",
  "time": { "epoch_ms": 1768440000789, "mono_ms": 123457455 },
  "type": "SET_YAW",
  "params": { "yaw_deg": 45.0, "duration_ms": 800 },
  "safety": { "max_rate_deg_s": 45.0 }
}

6.5 EventMsg（事件）

用于告警、状态变化、对外上报、状态机触发。

字段定义：

version: "0.1"

time: { epoch_ms, mono_ms }

type: "TARGET_DETECTED" | "TARGET_LOST" | "LINK_LOST" | "MODE_CHANGED"

severity: "INFO" | "WARN" | "ERROR"

ref（可选）:

observation_id?: string

note?: string

示例：

{
  "version": "0.1",
  "time": { "epoch_ms": 1768440000999, "mono_ms": 123457665 },
  "type": "LINK_LOST",
  "severity": "ERROR",
  "note": "MAVLink heartbeat missing > 5s"
}

7. Error Handling & Degradation（错误处理与降级原则）

v0.1 统一原则：

遥测链路 LOST：禁止输出控制指令（Control 进入抑制模式），FSM 进入 HOLD/STOP

单传感器失败：允许系统退化运行（例如仅视觉/仅音频），但必须输出 status=DEGRADED 或 INVALID

Logger 写失败：必须产生 EventMsg（severity=ERROR），并在控制台/日志中可见

8. Versioning Policy（版本策略）

所有消息必须携带 version

任何字段的语义变更、增删改必须：

升级版本号（例如 0.1 → 0.2）

更新本文档并记录变更

v0.1 冻结后，模块实现必须以文档为准，不允许“暗改字段”
