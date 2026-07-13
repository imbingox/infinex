# 前端开发规范

> 本目录记录当前 Infinex Web Console 已落地的实现边界。规范以 `web/` 源码、FastAPI 托管代码、`README.md` 与 CI 为依据，不把尚未采用的库或目录结构写成项目约定。

## 适用范围

前端代码位于 `web/`，当前技术基线为：

- React 19 单页应用，入口为 `web/src/main.tsx`，主要界面与状态集中在 `web/src/App.tsx`。
- Vite 开发与构建；`web/package.json` 声明 Vite `^7.0.0` 和 `@vitejs/plugin-react`。
- Bun 负责依赖锁定、脚本和测试；锁文件是 `web/bun.lock`。
- Ant Design 5 提供布局、表格、状态反馈和主题；ECharts 6 提供 Worker 状态环图。
- FastAPI 在生产运行时托管 `web/dist`，并提供静态文件与 SPA fallback。

## 规范索引

| Guide | 内容 | 状态 |
|-------|------|------|
| [Web Console 开发规范](./web-console-guidelines.md) | 文件职责、单页状态、API/DTO、状态展示、实时刷新、静态托管、测试与禁止模式 | 已填 |

## 开发前检查

- [ ] 阅读 [Web Console 开发规范](./web-console-guidelines.md)，再定位 `web/src/` 中已有的相邻实现。
- [ ] 判断改动属于 `App.tsx` 界面编排、`api.ts` HTTP 边界、`types.ts` DTO、`status.ts` 状态语义、`styles.css` 全局样式还是 Vite/FastAPI 托管边界。
- [ ] 涉及 API response 时，对照 `src/infinex/control_plane/api.py`、相关 SQLModel/Pydantic 定义和 `web/src/types.ts`；不要只改单侧字段。
- [ ] 涉及服务地址时，同时核对 `web/src/api.ts`、`web/vite.config.ts`、Socket.IO 初始化与生产 same-origin 行为。
- [ ] 涉及状态值时，同时核对后端状态字符串、`statusTone()`、表格/统计展示和 `web/src/status.test.ts`。
- [ ] 涉及 ECharts 或浏览器事件监听时，先设计组件卸载时的 `dispose`、`removeEventListener` 或连接关闭路径。
- [ ] 不默认存在 URL 路由、全局状态库、组件目录或浏览器 DOM 测试框架；当前仓库没有这些基础设施。

## 质量检查

前端改动交付前，从仓库根目录运行：

```bash
cd web
bun run typecheck
bun test
bun run build
```

这些命令分别对应 TypeScript `tsc --noEmit`、Bun 测试和 `tsc --noEmit && vite build`。当前 `web/package.json` 没有 `lint` script，不得把虚构的 lint 命令作为已存在的质量门禁。

跨层修改还应运行相关后端测试；后端入口与完整质量命令见 [后端开发规范](../backend/index.md)。

## 维护原则

规范正文使用中文，技术标识保持源码原文。更新本目录时，应以当前 `web/package.json`、`web/src/`、`src/infinex/control_plane/app.py`、`.github/workflows/ci.yml` 和实际测试为证据；当目录结构、工具链或托管方式真正变化后，再同步调整规范。
