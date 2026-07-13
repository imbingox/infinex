# Web Console 开发规范

> 本规范描述当前 `web/` 控制台的真实实现。它是一个 React 19 + Vite 单页应用，使用 Ant Design 展示控制面数据、ECharts 绘制 Worker 状态，并通过 HTTP 拉取完整状态、Socket.IO 接收刷新提示。

## 工具链与入口

`web/package.json` 是前端依赖和命令的权威来源：

- 运行时依赖声明为 React/React DOM `^19.1.0`、Ant Design `^5.26.0`、ECharts `^6.0.0`、Socket.IO Client `^4.8.1`。
- 构建工具声明为 Vite `^7.0.0`、TypeScript `^5.8.0` 和 `@vitejs/plugin-react`。
- 包管理与测试统一使用 Bun；不要把其他包管理器的命令写进开发或 CI 契约。
- `web/tsconfig.json` 开启 `strict`、`isolatedModules`、`noEmit`，目标为 `ES2022`，模块解析使用 `Bundler`。

入口链路是：

```text
web/index.html
  -> web/src/main.tsx
     -> Ant Design ConfigProvider + React StrictMode
        -> web/src/App.tsx
```

`main.tsx` 负责挂载 React root、加载 `styles.css` 和设置 Ant Design dark theme token。应用业务状态、导航、数据加载和当前页面渲染都在 `App.tsx`；不要把仓库当前并不存在的路由层或 store 层描述为既有架构。

## 文件职责与依赖边界

| 文件 | 当前职责 | 修改约束 |
|------|----------|----------|
| `web/src/main.tsx` | React root、`StrictMode`、Ant Design 全局主题 | 只放应用级 provider 和入口样式，不放 API 请求或页面状态 |
| `web/src/App.tsx` | 单页导航、HTTP/Socket.IO 刷新、表格、统计卡、部署动作、ECharts 组件 | 复用 `api.ts`、`types.ts`、`status.ts`，不要在 JSX 中复制跨页面契约 |
| `web/src/api.ts` | API base URL 归一化、JSON fetch、非 2xx 错误转换 | 所有常规 JSON HTTP 请求经过 `apiRequest<T>()` |
| `web/src/types.ts` | Web Console 实际消费的 response DTO | API 字段变化时与后端实现同步核对 |
| `web/src/status.ts` | 后端状态字符串到 Ant Design `Tag` tone 的集中映射 | 新状态只在此处集中分类，并同步测试 |
| `web/src/status.test.ts` | Bun 纯函数测试示例 | 使用 `bun:test` 的 `describe`、`test`、`expect` |
| `web/src/styles.css` | 全局页面、侧边栏、图表和 Ant Design 覆盖样式 | 延续现有 class 命名，谨慎使用 `!important` 覆盖组件样式 |

当前没有 `components/`、`pages/`、React Router 或状态管理库。若未来代码规模确实需要拆分，应在真实重构发生时同步更新本规范，而不是提前建立虚假的目录契约。

## 单页导航与本地状态

当前导航不是 URL 路由。`App.tsx` 用联合类型和组件内 state 选择页面：

```ts
type View = "overview" | "workers" | "strategies" | "backtests" | "deployments" | "audit";

const [view, setView] = useState<View>("overview");
```

Ant Design `Menu` 的 key、`View` 联合类型和 `page` 的条件分支必须保持一致。增加一个当前模式下的新视图时，至少同步：

1. `View` 的合法值。
2. `Menu.items` 的 key、icon 和 label。
3. `page` 中的渲染分支及所需数据。
4. 页面标题与空态、加载态、错误态。

侧边栏折叠状态保存到 `window.localStorage` 的 `infinex.sidebarCollapsed`。读取仅发生在 `useState` initializer，写入由对应 `useEffect` 完成；不要在每次 render 中直接写浏览器存储。

## 数据加载与实时刷新

`Console.loadData()` 是控制台状态同步的单一入口。它并行请求：

- `GET /api/summary`
- `GET /api/workers`
- `GET /api/strategies`
- `GET /api/backtests`
- `GET /api/deployments`
- `GET /api/audit-events?limit=50`

请求使用 `Promise.all()`，成功后一次更新六组 state，并清除全局错误。`requestInFlight` 防止初始加载、5 秒轮询、手动刷新和 Socket.IO 事件产生重叠请求。修改刷新机制时保留这一并发保护，避免旧响应覆盖新状态或刷新风暴。

加载模式有不同 UI 语义：

- `initial`：控制表格的 `initialLoading`，结束后必须清除初始 loading。
- `manual`：控制刷新按钮的 `refreshing`，结束后必须恢复按钮。
- `background`：轮询或事件触发，不打断当前页面。

Socket.IO 初始化遵循：

```ts
const socket = io(apiBaseUrl || window.location.origin, { path: "/socket.io" });
socket.on("system.updated", () => void loadData("background"));
```

`system.updated` 只表示“服务端状态可能变化”，不是前端状态的权威 payload。收到事件后仍通过 HTTP 重新拉取完整状态。组件卸载时必须 `clearInterval()` 并 `socket.disconnect()`；不要因已有 Socket.IO 通知而删除 5 秒 HTTP 收敛路径。

## HTTP 与服务地址

`web/src/api.ts` 定义唯一的 API base URL：

```ts
export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
```

行为契约如下：

- 未设置 `VITE_API_BASE_URL` 时，`apiBaseUrl` 为空字符串，`fetch("/api/...")` 使用浏览器当前 origin；Socket.IO 使用 `window.location.origin`。
- 设置 `VITE_API_BASE_URL` 时，HTTP 和 Socket.IO 都连接该 origin；末尾一个 `/` 会被移除，调用路径仍应以 `/api` 开头。
- Vite 开发服务器监听 `5173`，并把 `/api` 与 `/socket.io` 代理到 `http://127.0.0.1:8002`；Socket.IO 代理启用 `ws: true`。该端口必须与 `infinex serve` 默认值保持一致。

常规 JSON 请求必须复用 `apiRequest<T>()`：

```ts
const workers = await apiRequest<Worker[]>("/api/workers");
await apiRequest(`/api/deployments/${deployment.id}/start`, { method: "POST" });
```

该 helper 当前有明确限制：它总是设置 `Content-Type: application/json`，成功后总是调用 `response.json()`。文件下载、文本响应或 `204 No Content` 不能直接假设适用；遇到这些 response 类型时，应先扩展边界并增加相应测试，而不是在页面里散落另一套错误处理。

## API 错误处理

`apiRequest()` 对非 2xx response 的处理顺序是：

1. 尝试解析 JSON body。
2. JSON 解析失败时用 `response.statusText` 作为 `detail`。
3. 抛出 `Error(body.detail ?? `HTTP ${response.status}`)`。

界面按操作范围展示错误：

- 六组控制面数据加载失败时，`App.tsx` 保存 error message，并用 `Alert` 显示 `Control plane unavailable`；已有成功数据不会在 catch 中被主动清空。
- 部署 start/stop 失败时，用 Ant Design `message.error()` 显示操作级错误；成功时用 `message.success()`，随后后台刷新。
- 捕获值不是 `Error` 时使用稳定的英文 fallback 文案，不直接渲染未知对象。

不要静默吞掉请求失败，也不要只在 console 中记录用户可见操作的失败。当前 deployment start/stop 已有成功反馈、失败反馈和完成后的刷新，但按钮没有 per-row loading 或重复提交保护；这是现有缺口，不应被描述成已经落地的通用 mutation 模式。修改该路径或新增 mutation 时，需要明确是否补齐这些保护，并保持反馈与刷新时机一致。

## DTO 与跨层契约

`web/src/types.ts` 是手写 DTO，不是从 OpenAPI 自动生成。它描述控制台当前消费的字段子集，例如：

```ts
export interface Worker {
  id: string;
  role: "backtest" | "live";
  status: "online" | "degraded" | "offline";
  capacity: number;
  current_runs: number;
  last_heartbeat_at: string;
  metadata: Record<string, unknown>;
}
```

后端证据来自 `src/infinex/control_plane/api.py`：`worker_view()` 把模型的 `metadata_json` 暴露为 response 字段 `metadata`；`summary()` 返回与 `Summary` 接口对应的嵌套计数；deployment start/stop endpoint 返回包含 `deployment` 和 `command` 的 JSON 对象。

维护 DTO 时遵循：

- 字段名保持后端 JSON 的 snake_case，不在 fetch 层做隐式 camelCase 转换。
- 可缺失或为 `null` 的 UI 字段必须在 TypeScript 中显式表达，并在表格中提供 `"—"` 等展示 fallback。
- `BacktestRun.result.metrics` 是可选映射；读取 `total_return` 时保持 optional chaining，并区分 `undefined` 与数值 `0`。
- 时间字段按后端 ISO datetime 字符串接收，由 `formatTime()` 使用用户 locale 格式化；缺失值显示 `"—"`。
- 修改 API response 时，同时核对 `api.py`、后端 model/schema、`types.ts` 和实际 render 使用点。Pydantic request schema 不等于所有 response 的完整形状。

不要用 `as unknown as ...` 掩盖 DTO 不一致，也不要在多个组件中各自声明同一 API response 类型。

## 状态展示

所有通用状态标签通过 `StatusTag` 调用 `statusTone()`，显示文本统一转为大写。当前 tone 映射为：

| Tone | 状态值 |
|------|--------|
| `success` | `online`、`running`、`succeeded`、`published` |
| `processing` | `queued`、`claimed`、`starting`、`preparing`、`ready` |
| `warning` | `degraded`、`stopping`、`candidate` |
| `error` | `offline`、`failed` |
| `default` | 其他未知状态 |

新后端状态出现时，先判断语义再更新 `web/src/status.ts`，并在 `web/src/status.test.ts` 添加断言。不要在不同 table column 中写独立的颜色判断；未知状态保留 `default`，避免因新状态导致 render 失败。

Deployment 同时显示 `desired_state` 与 `actual_state`，中间使用箭头分隔。动作按钮依据 `desired_state === "running"` 选择 stop 或 start；不要只看 `actual_state` 推导用户请求意图。

## Ant Design、ECharts 与样式

页面布局和反馈优先复用当前 Ant Design 组件：`Layout`、`Menu`、`Table`、`Card`、`Statistic`、`Tag`、`Alert`、`Button`、`Tooltip` 与 `App.useApp().message`。表格必须设置稳定的 `rowKey="id"`，可选字段 render 时提供明确空值展示。

`WorkerChart` 的生命周期是当前 ECharts 参考模式：

- 首次 effect 中以 DOM ref 调用 `echarts.init()`，保存实例并注册 window resize handler。
- cleanup 中移除 resize handler、调用 `chart.dispose()` 并清空 ref。
- 单独 effect 监听 `summary`，用 `setOption()` 更新数据，不在每次数据变化时重新创建实例。

新增图表时复用该初始化、更新、销毁分离模式，避免重复实例和全局事件监听泄漏。

全局视觉基线位于 `main.tsx` 的 dark theme token 与 `styles.css`。当前 `body` 设置 `min-width: 1080px`，因此不能把现状描述为移动端自适应；若要支持窄屏，必须同时处理该最小宽度、侧边栏、表格溢出和图表尺寸，而不只是增加 Ant Design Grid breakpoint。

## 生产构建与 FastAPI 托管

生产构建命令是：

```bash
cd web
bun run build
```

Vite 输出到默认的 `web/dist`。`src/infinex/control_plane/settings.py` 的 `web_dist_dir` 默认也是 `Path("web/dist")`，`src/infinex/control_plane/app.py` 的托管行为为：

- `web/dist/assets` 存在时挂载为 `/assets` 静态目录。
- `/` 在 `index.html` 存在时返回 SPA 入口；未构建时返回包含服务名、`/docs` 和 `/api/health` 的 JSON 信息。
- catch-all route 对 `api/` 前缀明确返回 404，不能把未知 API 路径误回退到 HTML。
- dist 中存在的普通文件直接返回；其他非 API 路径在 `index.html` 存在时返回该入口，形成 SPA fallback。
- 未构建且无法找到文件时返回 404，detail 为 `Web console has not been built`。

不要在 Vite 配置和 FastAPI 中维护两套不一致的产物目录。生产环境默认应让前端与 API same-origin；只有明确的分离部署场景才设置 `VITE_API_BASE_URL`，并同时验证 HTTP、Socket.IO 和 CORS。

## 测试与验证

当前前端测试使用 Bun 内置 runner。`web/src/status.test.ts` 是可信的最小单元测试示例：从 `bun:test` 导入 `describe`、`test`、`expect`，测试无 DOM 的纯函数。

按改动选择测试：

- 修改状态分类：扩展 `web/src/status.test.ts`，覆盖新增状态和默认分支。
- 新增可独立计算的格式化、筛选或状态决策：优先提取为纯 `.ts` helper，并添加同目录 `*.test.ts`。
- 修改 DTO、table column 或 API 调用：至少依靠 `bun run typecheck` 检查字段与 render 契约，并运行完整 build。
- 修改 API response 或静态托管：除前端命令外，运行对应后端 API 测试。

仓库当前没有 jsdom、happy-dom 或 Testing Library 配置。需要 DOM/component 测试时，应先明确引入并配置真实测试环境；不要写依赖不存在环境的测试并声称当前 `bun test` 已覆盖浏览器行为。

交付前固定运行：

```bash
cd web
bun run typecheck
bun test
bun run build
```

`.github/workflows/ci.yml` 使用同一组三条命令。`bun run build` 已再次执行 `tsc --noEmit`，但本地和 CI 仍显式保留独立 typecheck 步骤，便于快速定位类型错误。

## 禁止模式

- 禁止虚构或依赖 `web/package.json` 中不存在的 `lint` script。
- 禁止把 React Router、Redux、Zustand 等未安装能力写成当前实现前提。
- 禁止绕过 `apiRequest()` 在 `App.tsx` 中复制 JSON base URL 和通用 HTTP 错误处理。
- 禁止把 Socket.IO event payload 当作完整状态，或移除 HTTP 轮询后的最终收敛能力。
- 禁止在 JSX 中复制 status-to-color 映射；统一维护 `status.ts`。
- 禁止用非空断言或双重类型断言掩盖 API 可空字段；应修正 DTO 与展示 fallback。
- 禁止创建 ECharts 实例后遗漏 `dispose()`、resize listener cleanup 或 Socket.IO disconnect。
- 禁止声称当前界面支持 URL 深链接或移动窄屏；现有实现分别没有 router，且 CSS 有 `min-width: 1080px`。
- 禁止修改公共 API 字段后只更新后端或只更新 `types.ts`；必须完成跨层核对和构建验证。
