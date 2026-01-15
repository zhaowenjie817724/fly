# Backlog (Sprint 1+)

## Sprint 1：采集层跑通 + 离线回放（可在无树莓派情况下先做 mock/格式）

1) Logger 目录与文件规范 v0
- 内容：定义 run_id 目录结构、manifest.json、jsonl 命名
- 验收：生成一套样例目录；回放脚本可读取 manifest 并定位文件

2) TelemetryCapture v0（真机或 SITL）
- 内容：读取 MAVLink heartbeat 与遥测，输出 TelemetryMsg（v0.1）
- 验收：每秒 >=1 条 TelemetryMsg；link_status 正确；示例日志符合 v0.1

3) VideoCapture v0
- 内容：采集视频帧/录像落盘（格式自定），输出 FrameMsg 或落盘索引
- 验收：运行 60 秒不崩；生成视频文件；日志含 fps/掉帧统计

4) AudioCapture v0
- 内容：采集多通道音频 chunk 并落盘（wav/pcm 皆可）
- 验收：运行 60 秒；文件可读；日志含 chunk 计数与丢块率

5) Replay v0
- 内容：按 time 回放 TelemetryMsg/ObservationMsg（mock 或真实）
- 验收：回放时序正确；输出流可用于 Service 推送或控制台打印

6) Service API v0（只实现最小 WS 推送可选）
- 内容：WebSocket 推送 Telemetry/Event（mock 数据亦可）
- 验收：客户端连接后能持续接收符合 v0.1 的消息
