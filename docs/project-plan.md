# Infinex 交易系统项目计划书

> 文档状态：实施基线 v0.2  
> 更新日期：2026-07-10  
> 当前阶段：阶段 1 平台基础闭环已完成，阶段 2 策略与回测闭环进行中（Mock Runtime）

### 当前实现快照

截至 2026-07-10，仓库已完成以下最小闭环：

- FastAPI Control Plane、SQLite/PostgreSQL 数据访问、REST API、OpenAPI 和 CLI 入口。
- Worker 注册令牌、每 Worker 独立凭据、心跳、后台离线收敛、Socket.IO 通知与 HTTP 周期同步。
- Live Agent 根据 Deployment 期望状态启动、停止和监控独立 Mock Runner 子进程。
- StrategyDraft、StrategyVersion、ConfigVersion、Bundle、SHA-256 和 JSON Schema 校验。
- BacktestRun 领取、租约、Artifact 下载校验、隔离 Mock Runner 和确定性回测结果。
- Deployment、Run、Command、AuditEvent 的基础状态与审计闭环。
- React、Vite、Bun、Ant Design 和 ECharts Web 控制台基础页面。
- Alembic 数据库迁移、Control Plane JSON 请求日志和带 PostgreSQL Service 的 CI。
- 后端 API 工作流、真实 Agent/Runner、Control Plane 重启、Socket.IO 重连、自动离线和 Runner 可复现性测试。
- 前端定时状态刷新、Vite API/Socket.IO 开发代理、类型检查、测试和生产构建。

阶段 1 的自动化验收覆盖以下故障边界：

- Live Agent 启动独立 Runner 并上报 Run/PID。
- Control Plane 停止和重启期间 Runner 保持运行。
- Agent 在 Control Plane 恢复后重新建立 Socket.IO 连接并继续状态收敛。
- Deployment 停止后 Runner 退出，Worker 停止心跳后由后台任务转为 offline。
- Worker 独立凭据不能用于冒充其他 Worker。
- Alembic 当前版本与模型元数据一致；PostgreSQL 迁移与读写测试由 CI 执行。

阶段 2 尚未完成的重点包括 NautilusTrader 接入、历史数据 Catalog、真实回测指标与成交明细、Bundle 内容寻址缓存、回测详情和多结果对比页面。

## 1. 项目概述

Infinex 是一个基于 NautilusTrader 的交易系统，统一支持策略回测和实盘运行。系统通过 Web 控制台管理策略版本、参数、回测任务、实盘部署和远程 Worker，并保证同一份策略代码能够在兼容的回测与实盘运行时中执行。

系统采用控制面与执行面分离的架构：

- Control Plane 维护系统的期望状态、配置、任务、审计和可视化数据。
- Worker Agent 部署在执行机器上，负责注册、心跳、状态收敛和 Runner 生命周期管理。
- Runner 是运行 NautilusTrader 策略实例的独立 Python 子进程。
- 策略代码以不可变、可校验、可分发的版本化 Bundle 存储，不与 Worker 平台代码绑定。

当前预计 Worker 总数不超过 20 个。系统优先减少部署组件和运维复杂度，不以大规模分布式平台为目标。

## 2. 项目目标

### 2.1 核心目标

- 在一个 Web 控制台中完成策略注册、回测、结果比较、实盘部署和运行控制。
- 使用同一策略 Bundle 支持回测与实盘，记录完整版本信息，确保结果可追溯。
- 支持本机 Backtest Worker 和远程 Live Worker。
- 一个 Live Worker 可以同时运行多个相互隔离的策略实例。
- 支持从 Web 修改策略版本和策略参数，并以受控方式应用到实例。
- 支持将回测中表现良好的策略版本与参数组合直接提升为实盘 Deployment。
- Control Plane 短暂不可用时，已运行的 Live Runner 不受影响。
- 所有关键操作、参数变更和运行结果均可审计。

### 2.2 非目标

首个版本暂不包含：

- 面向第三方的不可信策略代码托管。
- Kubernetes 或自研容器编排平台。
- 超过 20 个 Worker 的大规模调度。
- 高频原始行情经 Control Plane 转发。
- 多 Control Plane 实例 Active-Active。
- 自动策略优化、自动实盘晋级和无人审批发布。
- 跨策略共享账户；实盘账户或子账户由业务侧确保隔离。

## 3. 已确认的架构决策

| 领域 | 当前决策 |
| --- | --- |
| 交易框架 | NautilusTrader |
| Control Plane | Python + FastAPI，模块化单体 |
| Web 语言 | TypeScript，启用严格类型检查 |
| Web 框架与构建 | React + Vite |
| Web 包管理与脚本运行 | Bun，本地、CI 和容器构建保持一致 |
| UI 组件 | Ant Design |
| 图表 | Apache ECharts |
| Web 生产运行方式 | 构建为静态文件，由 FastAPI 或现有网关提供，不运行 Node.js/Bun 服务 |
| 事实数据存储 | PostgreSQL |
| 浏览器通信 | HTTP API + Socket.IO |
| Worker 通信 | HTTP API + Socket.IO，Worker 主动连接 |
| 消息可靠性 | PostgreSQL 持久化 + 期望状态收敛，Socket.IO 只负责即时通知 |
| Worker 运行方式 | 每台机器一个 Worker Agent，可管理多个 Runner 子进程 |
| 策略源码管理 | 首期由 Control Plane 管理策略草稿、源码快照和发布版本，Git 仅作为可选导入/导出能力 |
| 策略分发 | 不可变 Strategy Bundle，经 HTTPS 拉取并校验 SHA-256 |
| Artifact 存储 | 首期使用 Control Plane 服务器本地持久化目录 |
| 配置管理 | 不可变 ConfigVersion，禁止覆盖历史版本 |
| 实例变更 | 首期通过受控重启应用，暂不支持热更新 |
| NATS JetStream | 当前不引入，满足明确触发条件后再评估 |

## 4. 总体架构

```text
                         Control Plane

┌────────────────┐  HTTP / Socket.IO  ┌───────────────────────────┐
│ React Web      │ ◀────────────────▶ │ FastAPI Control Plane     │
│ Ant Design     │                    │                           │
│ ECharts        │                    │ API / Auth / Reconciler   │
└────────────────┘                    │ Scheduler / Audit / Files │
                                      └───────────┬───────────────┘
                                                  │
                                      ┌───────────┴───────────────┐
                                      │ PostgreSQL + Artifact Dir │
                                      └───────────┬───────────────┘
                                                  │
                         HTTP / Socket.IO / HTTPS Artifact Pull
                                                  │
              ┌───────────────────────────────────┴─────────────────┐
              │                                                     │
    ┌─────────▼──────────┐                               ┌──────────▼─────────┐
    │ Backtest Worker    │                               │ Live Worker        │
    │ Agent              │                               │ Agent              │
    │ ├─ Runner          │                               │ ├─ Live Runner A   │
    │ └─ Runner          │                               │ └─ Live Runner B   │
    └────────────────────┘                               └────────────────────┘
```

Control Plane 是管理中枢，但不是实时交易链路的一部分。Live Runner 直接连接行情源与交易所；Control Plane 故障时不应导致正在运行的策略被自动终止。

## 5. 组件职责

### 5.1 Web 控制台

Web 控制台只负责交互和展示，不承载 Worker 调度或交易业务逻辑。

主要页面：

- 总览：Worker、回测任务、实盘实例和异常概览。
- Worker：在线状态、容量、运行时版本、实例列表和最近心跳。
- 策略：Strategy、策略草稿、StrategyVersion、Manifest 和配置 Schema。
- 回测：创建任务、查看进度、指标、权益曲线、回撤和成交明细。
- 候选配置：从回测结果保存或提升 ConfigVersion。
- 实盘部署：选择 Worker、策略版本、配置版本、账户引用并进行准备。
- 实盘实例：启动、停止、升级、查看状态和运行历史。
- 审计：用户操作、配置变更、命令执行和失败原因。

### 5.2 Control Plane

Control Plane 首期作为单个 FastAPI 服务部署，内部保持模块边界：

- 身份认证与权限控制。
- Worker 注册、鉴权、心跳、容量和兼容性管理。
- Strategy、策略草稿、StrategyVersion 和 Bundle 元数据管理。
- ConfigVersion 的 Schema 校验和版本管理。
- BacktestRun 创建、领取、租约、状态和结果管理。
- Deployment 期望状态、修订版本和 Worker 分配管理。
- Command 持久化、幂等标识和执行状态管理。
- Worker 事件消费和实际状态更新。
- Socket.IO 连接与即时通知。
- Artifact 生成、上传、下载授权和校验信息管理。
- 审计日志。

Control Plane 不运行 NautilusTrader，不加载策略 Bundle，不持有交易所密钥明文，也不转发行情和订单。

### 5.3 Worker Agent

Agent 是每台 Worker 机器上的长期运行进程：

- 主动连接 Control Plane，无需开放入站控制端口。
- 注册 Worker 身份、角色、容量、平台和 Runtime 版本。
- 定期心跳，并周期性拉取期望状态以弥补 Socket.IO 消息丢失。
- 下载、校验和缓存 Strategy Bundle。
- 校验 StrategyVersion 与 Worker Runtime 的兼容性。
- 创建、停止、监控 Runner 子进程。
- 为每个 Runner 分配独立工作目录、配置快照和日志。
- 上报 Runner 状态、退出码和失败原因。
- Backtest Worker 负责领取任务、维护租约和限制并发数量。
- Agent 重启后识别遗留 Runner，或根据既定恢复策略重新收敛状态。

Agent 不执行具体策略逻辑，也不动态修改自身代码。

### 5.4 Runner

Runner 是独立 Python 子进程，每个进程只运行一个策略实例：

- Live Runner：长生命周期，运行一个实盘 Deployment 的一次 Run。
- Backtest Runner：短生命周期，完成一个 BacktestRun 后退出。
- 加载指定的 StrategyVersion 和不可变 ConfigVersion。
- 初始化 NautilusTrader、数据客户端和执行客户端。
- 输出结构化状态、日志、指标与结果。
- 接收优雅停止信号，并在超时后由 Agent 强制清理。

停止策略、撤销订单和清仓必须是不同的业务动作，不得把进程终止等同于自动清仓。

## 6. 策略管理、Bundle 与运行时

### 6.1 系统内置策略库

首期不强制策略代码使用 Git 管理。Control Plane 提供内置策略库，负责保存策略草稿、源码快照、发布版本和 Artifact 元数据。

策略代码可以通过 Web 上传、Web 编辑或本地 CLI 上传进入系统。上传后的内容先处于草稿状态，允许频繁修改；每次基于草稿发起回测时，系统自动创建一个不可变的 candidate StrategyVersion，并为该版本生成可分发的 Strategy Bundle。实盘部署只能使用 published StrategyVersion。

Git 不是运行时依赖，也不是 Worker 获取策略代码的入口。后续可以支持从 Git 导入、导出或记录 Git 引用，但实盘与回测始终只引用系统内的 StrategyVersion。

基本流程：

```text
策略草稿
  → 生成 candidate StrategyVersion 与不可变 Bundle
  → 回测迭代
  → 标记为 published StrategyVersion
  → Backtest / Live Worker 下载并校验 Bundle
```

StrategyVersion 必须绑定源码快照 Hash 和 Artifact SHA-256。策略草稿可以覆盖，StrategyVersion 不可覆盖。StrategyVersion 的状态可以在 `candidate`、`published` 和 `archived` 之间流转，但其源码快照和 Artifact 内容不可改变。

### 6.2 Bundle 格式

建议使用 Wheel 加 Manifest 的 Bundle：

```text
mean-reversion-1.3.0.bundle/
├── manifest.json
├── strategy.whl
├── config.schema.json
├── defaults.json
└── checksums.json
```

Manifest 至少包含：

- `strategy_id`
- `version`
- `entrypoint`
- `runtime_version`
- `config_schema_version`
- `artifact_sha256`
- `source_snapshot_sha256`
- 构建时间
- 可选的源码来源引用，如 Git repo、branch、commit 或上传者说明
- 可选的策略能力声明

StrategyVersion 不可覆盖。版本标签和 SHA-256 共同确定实际代码内容。

### 6.3 Runtime 兼容性

Worker Runtime 镜像统一提供：

- Python 版本
- NautilusTrader 版本
- 平台 Runner SDK
- 已支持的交易所与数据 Adapter
- 平台规定的公共依赖

Strategy Bundle 不携带自己的 NautilusTrader。Bundle 必须声明兼容的 `runtime_version`，Control Plane 和 Agent 都需要执行兼容性校验。

Backtest Worker 与目标 Live Worker 应使用相同 Runtime 版本。Runtime 升级后，策略必须重新构建并至少完成一次兼容性回测。

### 6.4 Artifact 分发

- Bundle 由 Control Plane 从 candidate 或 published StrategyVersion 生成，或由受信任 CLI 构建后上传。
- PostgreSQL 只保存元数据和校验值，不保存大型二进制文件。
- Worker 接到准备任务后，通过 HTTPS 主动下载 Bundle。
- Worker 下载后校验 SHA-256，再写入按内容寻址的本地缓存。
- Control Plane 不通过 Socket.IO 推送代码文件。
- Artifact 目录必须纳入备份策略。

后续若本地存储成为容量、备份或多实例部署瓶颈，再迁移到 S3/MinIO。

## 7. 核心领域模型

| 对象 | 说明 | 关键属性 |
| --- | --- | --- |
| Worker | 一台执行节点或一个 Agent 实例 | 角色、容量、Runtime、状态、最后心跳 |
| Strategy | 策略的逻辑身份 | 名称、描述、负责人 |
| StrategyDraft | 可变策略草稿 | Strategy、当前源码、默认参数、Schema、最后修改人 |
| StrategyVersion | 不可变策略代码版本 | 状态、源码快照、Bundle、SHA-256、Runtime 约束、Schema |
| ConfigVersion | 不可变参数快照 | StrategyVersion、JSON 配置、创建来源 |
| BacktestRun | 一次可复现回测 | 策略版本、配置版本、数据版本、Runtime、结果 |
| Deployment | 用户管理的稳定策略实例 | Worker、策略版本、配置版本、账户引用、期望状态 |
| Run | Deployment 的一次执行记录 | 实际版本、PID、开始/结束时间、退出原因 |
| Command | 一次控制操作 | message_id、类型、目标、状态、执行结果 |
| AuditEvent | 操作审计 | 操作者、对象、动作、前后差异、时间 |

Web 中的“策略实例”对应 Deployment。Deployment 可以经历多次启动、停止和升级，每次实际运行产生新的 Run。

## 8. 状态模型

### 8.1 Worker 状态

```text
REGISTERING → ONLINE → DEGRADED → OFFLINE
```

Worker 是否离线由最近心跳和会话租约共同判断，不能只依赖 Socket.IO 连接状态。

### 8.2 Deployment 实际状态

```text
CREATED
  → PREPARING
  → READY
  → STARTING
  → RUNNING
  → STOPPING
  → STOPPED
```

任一准备或运行阶段都可能进入 `FAILED`。失败状态必须包含结构化原因和可读错误信息。

Deployment 同时保存：

- `desired_state`
- `actual_state`
- `desired_revision`
- `actual_revision`
- `desired_strategy_version`
- `actual_strategy_version`
- `desired_config_version`
- `actual_config_version`

Agent 根据期望值与实际值的差异执行收敛。

### 8.3 BacktestRun 状态

```text
QUEUED → CLAIMED → RUNNING → SUCCEEDED
                           └→ FAILED
             └→ LEASE_EXPIRED → QUEUED
```

Backtest Worker 使用有过期时间的任务租约。Agent 或 Runner 崩溃后，任务可以重新进入队列。

## 9. 核心工作流

### 9.1 策略注册与回测

1. 开发者在 Web 或本地 CLI 中创建或更新策略草稿。
2. Control Plane 保存草稿源码、默认参数和配置 Schema。
3. 用户基于草稿发起回测时，系统自动创建 candidate StrategyVersion。
4. Control Plane 生成不可变 Bundle，并完成格式、Schema、Runtime 和 SHA-256 校验。
5. Web 选择 StrategyVersion、数据集和参数创建 BacktestRun。
6. Backtest Worker 领取任务并准备 Bundle。
7. Agent 创建 Backtest Runner。
8. Runner 完成回测并提交结果与运行元数据。
9. Web 使用 ECharts 展示结果并支持多个 BacktestRun 比较。
10. 回测表现满足要求后，用户将该 StrategyVersion 标记为 published，供实盘 Deployment 使用。

### 9.2 从回测提升到实盘

1. 用户选择一个成功的 BacktestRun。
2. 系统从该回测保存或复用 ConfigVersion，禁止手工重新录入参数。
3. 用户创建 Deployment，选择目标 Worker 和账户凭据引用。
4. Control Plane 将 Deployment 设为 `PREPARING`。
5. Worker 下载 Bundle、校验 Runtime 和配置，报告 `READY`。
6. 用户确认后将 `desired_state` 设置为 `RUNNING`。
7. Agent 创建 Live Runner 并报告实际状态。

### 9.3 修改参数或策略版本

1. Web 根据该 StrategyVersion 的 JSON Schema 展示参数表单。
2. 保存时创建新的 ConfigVersion，不覆盖旧记录。
3. 用户选择“保存但不应用”或“保存并应用”。
4. 应用前，Agent 先下载并校验新 Bundle 与配置。
5. 准备失败时，旧 Runner 保持运行。
6. 准备成功后，Agent 按明确的升级策略停止旧 Runner，再启动新 Runner。
7. 创建新的 Run，并保留旧 Run 的完整历史。

首期所有策略版本和参数变更均通过重启生效。热更新需要策略主动实现并声明字段级能力，后续单独设计。

### 9.4 停止、撤单与清仓

Web 必须提供语义明确且权限不同的操作：

- 停止策略：停止产生新决策，按策略约定处理当前订单。
- 撤销订单：撤销该 Deployment 拥有的未完成订单。
- 清仓：将该隔离账户的仓位降为零。
- 紧急停止：执行预定义的撤单、清仓或停止组合。

具体语义、审批与确认交互需要在开发前确定。

## 10. 通信与可靠性

### 10.1 基本原则

- PostgreSQL 是系统事实来源。
- Socket.IO 只用于降低通知延迟，不承担持久化责任。
- Control Plane 先提交数据库事务，再发出 Socket.IO 通知。
- 通知发送失败不会丢失业务状态，Worker 通过周期同步最终收敛。
- Worker 每次重连必须重新获取完整期望状态和未完成命令。
- 命令采用 `message_id` 幂等处理。
- Worker 不信任只从 Socket.IO 收到的完整配置，必须按版本向 API 获取并校验。

### 10.2 消息信封

```json
{
  "message_id": "uuid",
  "schema_version": 1,
  "type": "APPLY_DEPLOYMENT",
  "worker_id": "live-worker-01",
  "deployment_id": "deployment-123",
  "desired_revision": 7,
  "created_at": "2026-07-10T00:00:00Z"
}
```

Agent 内部保留 Transport 接口，使通信实现不侵入生命周期和状态收敛逻辑。当前仅实现 Socket.IO Transport。

### 10.3 NATS 引入条件

出现以下任一明确需求时，再评估 NATS JetStream：

- Control Plane 需要多实例 Active-Active。
- Backtest Worker 扩展为多机器高并发任务池。
- Worker 事件需要被多个独立服务分别消费和重放。
- 状态、日志或交易事件吞吐开始影响 Control Plane。
- 出现跨区域、长期离线和大量积压消息消费需求。

仅仅因为 Worker 位于远程机器，不构成引入 NATS 的理由。

## 11. 多实例隔离

一个 Live Worker 可以运行多个 Runner，每个 Runner 至少具备：

- 独立 Python 进程和 NautilusTrader 实例。
- 独立工作目录、配置文件和日志文件。
- 独立 DeploymentId、RunId、TraderId 和 StrategyId。
- 独立账户或交易所子账户凭据。
- 独立订单 Client ID 命名空间。
- 独立的生命周期和失败状态。
- 可配置的 CPU、内存或 Runner 数量上限。

当前假设策略代码由内部可信团队提供。独立进程提供故障隔离，但不是安全沙箱。未来若需要运行不可信代码，应切换为每 Runner 容器或更严格的沙箱方案。

## 12. 安全设计基线

- 所有远程通信使用 TLS。
- Worker 使用独立机器身份和可撤销凭据。
- Worker 主动连接 Control Plane，不开放远程控制端口。
- 交易所密钥仅保存在 Live Worker 本地 Secret 中。
- Control Plane 只保存 Secret 引用和非敏感元数据。
- Artifact 下载需要 Worker 身份认证，并校验 SHA-256。
- Web 操作采用 RBAC，至少区分查看、回测、部署、启动停止和紧急操作权限。
- 参数变更、策略升级、启动、停止、撤单和清仓全部记录审计日志。
- 敏感字段不得进入普通日志、Socket.IO Payload 或回测结果。

## 13. 前端方案

### 13.1 技术选型

前端技术组合确定为：

```text
TypeScript + React + Vite + Ant Design + ECharts
包管理与脚本 Runtime：Bun
```

各组件职责如下：

- TypeScript：前端开发语言，启用严格类型检查；React 组件使用 `.tsx`，其余模块使用 `.ts`。
- React：组织页面、组件和交互状态。
- Ant Design：布局、表格、表单、抽屉、弹窗、步骤、状态标签和权限控制界面。
- ECharts：权益曲线、回撤、收益分布、持仓、PnL、成交点位和多回测对比。
- Vite：提供本地开发服务，并将 TypeScript 和 React 构建为静态文件。
- Bun：安装前端依赖，运行 Vite、类型检查、测试和构建脚本。

本地和 CI 使用统一命令：

```bash
bun install --frozen-lockfile
bun run typecheck
bun run test
bun run build
```

项目只保留 `bun.lock`，不混用 npm、pnpm 或 Yarn 的锁文件。

生产构建产物为 `index.html`、CSS 和 JavaScript 等静态文件，由 FastAPI 或现有网关直接提供。Bun 只存在于开发、CI 和容器构建阶段，不作为生产服务运行。

不使用 Next.js，原因是系统是登录后的操作型控制台，不依赖 SEO、SSR 或 React Server Components。这样线上无需额外运行 Node.js 或 Bun 服务。

### 13.2 设计约束

- Web 只调用 Control Plane，不直接访问 Worker。
- 配置表单由 `config.schema.json` 驱动，但危险参数需要专门交互，不能完全依赖自动表单。
- 表格适合状态扫描和批量比较，避免把操作台设计成大量装饰性卡片。
- ECharts 只负责可视化，原始指标和聚合逻辑由后端定义。
- 大量成交点或时间序列需要后端聚合或降采样，不能一次性传输全部数据。
- 启动、停止、升级、撤单和清仓必须展示当前状态、目标状态和执行结果。

### 13.3 首期页面范围

1. 登录与基础权限。
2. 系统总览。
3. Worker 列表与详情。
4. Strategy 与 StrategyVersion 管理。
5. BacktestRun 创建、列表、详情与对比。
6. ConfigVersion 管理。
7. Deployment 创建、准备、启动、停止和升级。
8. Run 详情、日志和状态时间线。
9. 审计日志。

## 14. 部署方案

### 14.1 Server 机器

```text
Docker Compose
├── control-plane
├── postgres
└── backtest-worker
```

持久化目录：

```text
/var/lib/infinex/postgres
/var/lib/infinex/artifacts
/var/lib/infinex/backtests
```

前端使用 Bun 和 Vite 在 CI 或 Docker 多阶段构建的前置阶段生成静态文件。构建产物复制进 Control Plane 镜像或挂载到静态目录；最终生产镜像不需要包含 Bun 或 Node.js Runtime。

### 14.2 Live Worker 机器

```text
Docker Compose
└── live-worker
    ├── Agent 主进程
    ├── Runner 子进程 1..N
    └── 持久化 Bundle、工作目录和日志缓存
```

Agent 容器配置包括：

- Worker ID 与角色。
- Control Plane 地址。
- Worker 身份凭据。
- Runtime 版本。
- 最大 Live Runner 数量。
- 本地 Secret 和持久化目录。
- 断网和进程恢复策略。

若未来需要为每个 Runner 设置强制 cgroup 资源限制，可以将 Agent 改为宿主机 systemd 服务并通过 transient unit 启动 Runner；这不是首期必要条件。

## 15. 可复现性要求

每个 BacktestRun 和 Live Run 至少记录：

- StrategyVersion 与 Artifact SHA-256。
- 源码快照 Hash 和可选源码来源引用。
- ConfigVersion 与配置内容 Hash。
- Worker Runtime、Python 和 NautilusTrader 版本。
- 历史数据集版本和时间范围。
- 撮合、费用、滑点和延迟模型版本。
- 交易所 Adapter 版本。
- 时区和时钟信息。
- 随机种子（如适用）。

从回测提升到实盘时，系统引用原有 StrategyVersion 和 ConfigVersion，不复制或重新录入内容。

## 16. 测试与验收策略

### 16.1 测试层级

- 单元测试：状态机、配置校验、兼容性、幂等和权限。
- 协议测试：Control Plane 与 Agent 的请求、事件和版本兼容。
- 集成测试：PostgreSQL、Socket.IO、Artifact 下载和 Runner 生命周期。
- 回测一致性测试：固定数据、版本和配置得到稳定结果。
- 故障恢复测试：Control Plane、Agent、Runner 和网络分别中断后的恢复。
- 模拟实盘测试：使用 sandbox/testnet 验证订单、撤单、重连和对账。
- 安全测试：权限、Secret 泄漏、Artifact 篡改和越权命令。

### 16.2 首期验收标准

- 可以创建策略草稿，自动生成 candidate StrategyVersion，并在 Web 查看其 Schema 和版本信息。
- 可以创建回测任务并得到可复现结果。
- 可以将成功回测的 StrategyVersion 标记为 published，并创建实盘 Deployment。
- 可以选择一个在线 Live Worker 完成准备、启动和停止。
- 同一个 Live Worker 可以同时运行至少两个独立 Runner。
- 修改参数会产生新的 ConfigVersion，并保留完整历史。
- Socket.IO 断开和重连后，Worker 能恢复到数据库中的期望状态。
- Runner 崩溃不会导致 Agent 或其他 Runner 退出。
- Control Plane 重启不会主动终止已经运行的 Live Runner。
- 所有关键操作能够在审计日志中追踪。

## 17. 实施阶段

### 阶段 0：需求与协议冻结

交付物：

- 补全本计划书中的待决事项。
- 确定首批交易所、数据源和 NautilusTrader 版本。
- 定义策略草稿、源码快照、发布和版本归档规则。
- 定义 Strategy Bundle、Manifest 和 Config Schema 规范。
- 定义 Deployment、Run、Command 状态机。
- 定义 Agent 通信协议和版本兼容策略。
- 完成数据库核心模型草案和 API 草案。

### 阶段 1：平台基础闭环

交付物：

- Control Plane、PostgreSQL 和 Web 工程骨架。
- Worker 注册、认证、心跳和状态展示。
- Socket.IO 通知与周期状态同步。
- Agent 启动、停止测试 Runner 的最小闭环。
- 基础审计和结构化日志。

### 阶段 2：策略与回测闭环

交付物：

- 策略草稿、发布、Strategy Bundle 构建、校验和缓存。
- StrategyVersion 与 ConfigVersion 管理。
- Backtest Worker、任务租约和 Runner 隔离。
- 回测指标、权益曲线、回撤、成交明细和对比页面。
- 回测可复现性检查。

### 阶段 3：实盘部署闭环

交付物：

- Deployment 准备、启动、停止和升级。
- 一个 Agent 管理多个 Live Runner。
- Worker 本地 Secret、账户隔离和订单归属。
- testnet/sandbox 交易验证。
- 断线、重连、进程崩溃和启动对账。

### 阶段 4：生产加固

交付物：

- RBAC 和敏感操作确认。
- 紧急停止、撤单和清仓流程。
- 备份、恢复和 Artifact 保全。
- 资源限制、日志保留和基础告警。
- 灰度升级与回滚流程。
- 上线运行手册和故障处理手册。

## 18. 开发前待决事项

以下问题会影响实现，进入阶段 1 前应逐项确认：

1. 首批支持的交易所、经纪商和账户类型。
2. NautilusTrader 目标版本及升级策略。
3. 历史数据来源、格式、Catalog 组织方式和数据版本定义。
4. 回测撮合、费用、滑点和延迟模型。
5. 策略草稿支持 Web 编辑、文件上传、本地 CLI 上传中的哪些入口。
6. 策略允许使用的第三方依赖范围。
7. Worker Runtime 与 StrategyVersion 的兼容规则。
8. Live Runner 启动时的账户、订单和仓位对账规则。
9. Control Plane 失联时 Live Runner 的默认行为。
10. Agent 或 Worker 机器重启后的 Runner 恢复策略。
11. 停止、撤单、清仓和紧急停止的精确定义。
12. 是否需要策略状态持久化和跨 Run 恢复。
13. 单 Worker 最大 Runner 数量及 CPU、内存限制。
14. Web 用户模型、RBAC 角色和高风险操作审批要求。
15. 回测结果需要保留的指标、图表和原始产物。
16. 日志保留周期、备份周期和恢复目标。
17. 是否需要 Git 导入、导出或仅记录可选 Git 来源引用。

## 19. 主要风险

| 风险 | 影响 | 初步应对 |
| --- | --- | --- |
| 回测与实盘 Runtime 不一致 | 回测结果不可复现 | Runtime 版本绑定，晋级时强校验 |
| 动态策略依赖冲突 | Runner 无法加载或行为不一致 | 限制依赖，Bundle 声明 Runtime 兼容性 |
| Socket.IO 消息丢失 | Worker 未及时执行命令 | PostgreSQL 持久化、周期同步、幂等收敛 |
| Agent 重启后子进程状态不明 | 重复运行或状态错误 | PID/Run 元数据、启动扫描、唯一实例锁 |
| 参数或版本升级失败 | 实盘中断 | 先准备后切换，旧 Runner 在准备失败时保持运行 |
| Artifact 被覆盖或篡改 | 回测与实盘代码不一致 | 不可变版本、SHA-256、访问控制和备份 |
| 策略草稿被覆盖 | 无法复现历史回测或实盘 | 生成 StrategyVersion 时创建不可变源码快照，Run 只引用 StrategyVersion |
| 多 Runner 争抢机器资源 | 延迟、OOM 或级联失败 | 并发上限、资源监控，必要时引入 cgroup |
| Control Plane 保存敏感信息 | 凭据泄漏 | Secret 仅驻留 Worker，Control Plane 保存引用 |

## 20. 后续可选能力

这些能力不进入首期范围，仅保留演进接口：

- NATS JetStream 和多 Control Plane 实例。
- S3/MinIO Artifact 与回测产物存储。
- 自动 Worker 调度与容量评分。
- 策略参数热更新。
- 策略状态快照与迁移。
- Prometheus、Grafana 和集中式日志平台。
- 自动参数搜索和回测实验管理。
- Git 导入、导出和策略源码同步。
- 多人审批、发布窗口和策略灰度升级。
- 每 Runner 容器或安全沙箱。

---

本计划书是当前架构与实施基线。后续开发应继续更新“当前实现快照”“已确认的架构决策”和“开发前待决事项”；在进入真实交易接入前，必须冻结关键协议、状态模型和安全语义。
