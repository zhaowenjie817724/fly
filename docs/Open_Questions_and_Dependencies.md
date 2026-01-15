# Open Questions & Dependencies

说明：本表用于把“当前不确定的硬件/接口事实”显性化，形成可追踪任务。每条依赖必须有 Owner 与 Due。

| ID | 问题/依赖 | 需要的最终答案（必须具体） | Owner | Due | 不解决会卡住什么 |
|---|---|---|---|---|---|
| D1 | 飞控型号与固件 | PX4/ArduPilot，版本号 | TBD | YYYY-MM-DD | MAVLink 消息集与参数 |
| D2 | MAVLink 输出方式 | USB/TELEM UART/UDP；波特率；MAVLink1/2 | TBD | YYYY-MM-DD | TelemetryCapture 无法落地 |
| D3 | 串口设备名 | 伴侣机上设备路径（示例：/dev/ttyACM0） | TBD | YYYY-MM-DD | 无法配置连接串口 |
| D4 | 摄像头接口与参数 | 分辨率、FPS、接口（USB/CSI），驱动方式 | TBD | YYYY-MM-DD | VideoCapture 性能预算 |
| D5 | 麦阵参数 | 通道数、采样率、数据格式、接口 | TBD | YYYY-MM-DD | AudioCapture 与 DOA 输入 |
| D6 | 热像是否接入 | 是否上热像；若上：分辨率/帧率/接口 | TBD | YYYY-MM-DD | ThermalCapture 与融合策略 |
| D7 | 传感器安装坐标系 | 机体前向定义、安装偏角（yaw offset） | TBD | YYYY-MM-DD | bearing 与控制方向一致性 |
| D8 | 控制权限与安全策略 | 是否允许自动控制；允许哪些指令 | TBD | YYYY-MM-DD | Control/FSM 安全边界 |
| D9 | 外部客户端形式 | 上位机/小程序/网页？协议偏好 WS/HTTP？ | TBD | YYYY-MM-DD | Service API 口径 |
| D10 | 数据落盘存储预算 | 运行时长、存储容量、是否循环覆盖 | TBD | YYYY-MM-DD | Logger/Replay 策略 |
