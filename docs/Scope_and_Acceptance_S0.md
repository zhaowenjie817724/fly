bearing 坐标系规则会在接口文档里冻结；这里主要冻结 Sprint 0 的验收裁判（DoD）。

# Sprint 0 Scope & Acceptance

## 1. Sprint 0 目标

Sprint 0 的目标是建立无人机软件系统的工程化地基，并冻结接口合同 v0.1，使后续 Sprint 能够并行开发、稳定联调、可复现问题。

Sprint 0 聚焦：
- 冻结软件架构与接口合同（v0.1）：模块边界、消息字段、端口/协议、错误/降级原则、版本策略
- 形成可追溯的依赖与风险管理：未决事项清单、风险登记表，关键条目 issue 化
- 让 Sprint 1 “可直接开工”：Backlog 拆分到单人可执行粒度，且每条有验收口径

## 2. Sprint 0 交付物

仓库中必须出现并可阅读以下文件（main 分支最终结果）：
- docs/Architecture_Interface_v0.1.md
- docs/Scope_and_Acceptance_S0.md
- docs/Open_Questions_and_Dependencies.md
- docs/Risk_Register.md
- backlog/Backlog_Sprint1_onward.md

## 3. Definition of Done（DoD：可验证验收标准）

以下条款全部满足，Sprint 0 才算完成（每条必须可通过“看文件/看示例/看 issue”验证）：

### 3.1 接口合同冻结（v0.1）
- docs/Architecture_Interface_v0.1.md 完整且包含：
  1) 模块表（职责/输入/输出/失败与降级）
  2) 至少 4 条端到端数据流（Dataflow）
  3) Message Spec v0.1：Observation / Telemetry / Command / Event
  4) Ports & Protocols：MAVLink、内部消息通信方式、对外 API 协议口径
  5) 版本策略：接口字段变更必须升级版本并记录变更

### 3.2 示例与可验证性
- Architecture_Interface_v0.1.md 中必须提供：
  - ObservationMsg 示例 JSON（可直接用于 mock）
  - TelemetryMsg 示例 JSON（可直接用于 mock）
- 示例字段与语义必须与 v0.1 规范一致

### 3.3 依赖可追踪
- docs/Open_Questions_and_Dependencies.md 不少于 10 条依赖/未决事项
- 每条包含：需要的最终答案、Owner、Due、影响（不解决会卡住什么）
- 关键依赖已在 GitHub Issues 建立（可指派、可跟踪）

### 3.4 风险可执行
- docs/Risk_Register.md 不少于 6 条风险
- 每条风险包含：触发条件、影响、监控指标、缓解动作、Owner
- 至少 3 条关键缓解动作已在 GitHub Issues 建立

### 3.5 Sprint 1 可开工
- backlog/Backlog_Sprint1_onward.md 中包含 Sprint 1 任务拆分
- 每条任务必须给出验收标准（可验证的输出/行为）

## 4. Non-Goals（Sprint 0 不做）

Sprint 0 不实现以下内容：
- 不实现视觉/音频/热像算法本体（仅冻结接口与消息合同）
- 不实现完整闭环控制（仅冻结控制指令接口与安全边界）
- 不实现小程序或上位机 UI（仅冻结对外接口字段/协议口径）
- 不做系统性能调优与长期稳定性测试
