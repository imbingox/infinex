# 日志规范

> Control Plane 向 stdout 输出统一 JSON line；Worker 目前把 JSON event 作为 message 交给 `logging.basicConfig()`，其默认 stream 是 stderr。进程管理器应同时收集两个标准流；进程集成测试会用 `stderr=STDOUT` 合并它们。

## Control Plane JSON 日志

`src/infinex/control_plane/logging.py` 定义 `JsonFormatter` 与 `configure_logging()`。固定基础字段为：

```json
{
  "timestamp": "UTC ISO-8601",
  "level": "info",
  "logger": "infinex.control_plane.http",
  "message": "http_request"
}
```

formatter 只从 `LogRecord` 提取已支持的额外字段：

```text
request_id, method, path, status_code, duration_ms,
event, object_id, worker_id
```

需要可查询的新字段时，先扩展 formatter 和 `tests/test_logging.py`，再在 call site 通过 `extra={...}` 写入；不要把结构化数据拼到自由文本。

`configure_logging()` 清理 root handlers、安装 stdout JSON handler，并把 `httpx` 降到 WARNING。FastAPI lifespan 与 `infinex serve` 都会调用它；新增库 logger 使用 `logging.getLogger(__name__)`，不要再私自添加 handler。

## HTTP 请求日志

`RequestLoggingMiddleware` 为每个请求：

1. 复用 `X-Request-ID` header，缺失时生成 UUID hex。
2. 用 `time.perf_counter()` 计算 `duration_ms`。
3. 成功后写 `http_request`，包含 method/path/status/duration，并把 request id 回写响应头。
4. 未处理异常写 `http_request_failed` 与 traceback，然后重新抛出交给 FastAPI。

参考调用：

```python
logger.info(
    "http_request",
    extra={"request_id": request_id, "method": request.method, "path": request.url.path},
)
```

不要记录 query/body/header 全量内容；其中可能包含 token、账户引用或策略配置。

## Worker 事件日志

`worker/agent.py` 与 `worker/backtest.py` 目前使用同名 `log_event()`，把 `event` 和字段序列化为稳定排序 JSON，再交给 logger：

```python
log_event("runner_started", deployment_id=deployment_id, generation=generation, pid=pid)
```

已有事件命名使用小写 `snake_case` 与完成语义，例如：

- 生命周期：`agent_registered`、`agent_socket_connected`、`agent_socket_disconnected`
- Runner：`runner_started`、`runner_stopped`、`runner_exited`
- Backtest：`backtest_worker_registered`、`backtest_succeeded`、`backtest_failed`
- 可恢复故障：`agent_sync_failed`、`agent_socket_unavailable`、`backtest_worker_sync_failed`

新事件沿用 `<subject>_<past-tense/action>`，至少带可关联的 `worker_id`、`deployment_id` 或 `run_id`。`tests/test_process_integration.py` 会按 JSON event 文本确认 Socket.IO 重连，因此重命名事件需要同步测试。

## Level 与异常

当前 Control Plane 的正常请求和 Worker 的 `log_event()` 都使用 `INFO`；`httpx` logger 被整体调到 `WARNING`，后台 sweep 的非预期异常使用 `logger.exception()`。在当前机制下按以下边界维护：

- `DEBUG`：高频、只用于临时诊断且默认不需要的内部细节。
- `INFO`：注册、状态变化、进程启动/停止、一次同步结果等正常事件。
- `WARNING`：当前主要用于抑制 `httpx` 低级别请求噪声；若要把 Worker 可恢复故障从现有 `INFO` 拆成 WARNING，应同时调整 `log_event()` 接口和测试。
- `ERROR/exception`：Control Plane 后台循环等非预期失败，需要 traceback 定位。

不要用 error level 记录合法的 4xx 业务拒绝；HTTP access log 已包含状态码。捕获非预期异常时使用 `logger.exception()` 或提供明确 error 字段，不要只写“failed”。

## 敏感信息

禁止记录：

- `WORKER_ENROLLMENT_TOKEN` 与每 Worker 独立 credential。
- `credential_hash`、Authorization/`X-Worker-Token` headers。
- 完整数据库 URL、环境变量、账户密钥和未脱敏策略配置。
- Artifact 内容与完整 bundle 源码。

允许记录资源 ID、runtime version、PID、状态、受控路径、checksum 和不含秘密的错误摘要。Worker credential 文件权限必须保持 `0600`，参考 `tests/test_process_integration.py`。

## 验证

修改 formatter/middleware：

```bash
uv run pytest tests/test_logging.py tests/test_api_workflow.py
```

修改 Worker event 或重连行为：

```bash
uv run pytest tests/test_process_integration.py
```

同时人工检查一条成功日志和一条异常日志能被逐行 JSON 解析，且没有 secret/header/body 泄漏。
