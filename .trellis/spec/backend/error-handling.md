# 错误处理规范

> 错误在最接近协议的边界被转换：请求 shape 由 Pydantic 处理，领域冲突由 API/service 转成 HTTP 状态，Worker/Runner 失败通过持久化状态上报。

## API 错误契约

当前 API 使用 FastAPI 默认 `{"detail": ...}` 错误 body。按现有代码选择状态码：

| 状态 | 当前含义 | 参考 |
|------|----------|------|
| `401` | Worker enrollment token/独立 credential 无效 | `api.require_worker_identity()`、`register_worker()` |
| `403` | credential 有效但操作属于另一个 Worker | `assert_worker_owns()`、`acknowledge_command()` |
| `404` | entity、artifact 或静态资源不存在 | `services.get_or_404()`、`download_strategy_artifact()`、`app.py` |
| `409` | 状态/关联/唯一约束冲突 | `publish_version()`、`assert_worker_compatible()`、`api.commit()` |
| `422` | Pydantic 字段校验或 JSON Schema config 校验失败 | `schemas.py`、`services.validate_config()` |

找实体时复用统一 helper：

```python
def get_or_404(session: Session, model: type, object_id: str):
    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return item
```

不要把所有业务拒绝都返回 400。当前实现把“合法请求但与当前资源状态冲突”映射为 409，把 schema/config 内容无效映射为 422。

## 数据库错误

route 的 `commit(session)` 捕获 `IntegrityError`，先 `rollback()` 再抛出 409 `Database constraint conflict`。调用方不应收到 SQL traceback、表结构或数据库凭据。

可预先判断的领域约束仍应在 commit 前检查并给出可读 detail，例如：

- ConfigVersion 不属于请求中的 StrategyVersion。
- Live deployment 使用了未 published version。
- Worker runtime 与 StrategyVersion runtime 不一致。
- 一个 deployment 已有 active run。

预检查改善协议反馈，数据库 constraint 仍是最终一致性防线。

## 后台循环与取消

无限循环只能在循环边界降级失败。`maintenance.worker_status_loop()` 的模式是：

```python
except asyncio.CancelledError:
    raise
except Exception:
    logger.exception("worker_status_sweep_failed")
```

- `CancelledError` 必须重新抛出，使 FastAPI lifespan 能正常停止任务。
- 其它异常用 `logger.exception()` 保留 traceback，等待下一 sweep 重试。
- 不要在 service/helper 内用裸 `except Exception` 返回默认成功；这会掩盖状态写入失败。

## Worker、HTTP Client 与 Runner

- `ControlPlaneClient` 每个请求调用 `response.raise_for_status()`；协议失败以 `httpx.HTTPError` 交给 Worker loop 统一处理。
- Live/Backtest Worker 的外层循环捕获网络、OS 和运行时错误，写结构化失败事件，然后继续下一次同步。
- 单次 Backtest 执行失败必须调用 `/backtests/{id}/complete`，将 `status=failed` 与可读 `error` 持久化；不能只写本地日志。
- Runner 非零退出时优先使用 stderr，其次 stdout，并限制上报尾部长度。参考 `BacktestWorker._execute()` 的 `error[-4000:]`。
- Live Runner 意外退出由 `_report_unexpected_exits()` 转换成 failed run/deployment 上报；控制面断开本身不应杀死仍在运行的子进程，进程集成测试覆盖了重连恢复。

当前 Worker 最外层允许捕获 `Exception` 的位置，是单个任务或进程生命周期隔离边界；内部仍应抛出具体异常，不能静默跳过 artifact hash、credential 或状态校验。

## Web 与跨层错误

`web/src/api.ts` 是浏览器错误转换边界：非 2xx 尝试读取 `detail`，否则 fallback 到 `HTTP <status>`。React 组件捕获 `Error`，向 Ant Design message/Alert 提供可读信息，同时保留已加载状态。

新增 API error shape 时必须同步更新 `apiRequest()` 和相关测试；不要让页面逐处解析不同的错误结构。

## 安全与禁止模式

- 错误和日志中不得包含 enrollment token、Worker credential、数据库 URL、完整账户密钥或策略私密配置。
- 不要把 `credential_hash` 当成可返回的诊断字段。
- 不要捕获异常后仍把 command/backtest 标成 succeeded。
- 不要仅依赖 Socket.IO 报错；需要恢复的事实必须进入数据库状态、command result 或 backtest error。
- 不要在 API 中返回原始 `IntegrityError`、subprocess 环境变量或不受限的完整 stderr。

## 测试要求

错误路径应断言状态码和关键 detail/状态，不只断言“请求失败”。参考：

- `tests/test_api_workflow.py`：无 token 为 401、冒用 credential 为 401、config 无效为 422。
- `tests/test_process_integration.py`：Control Plane 重启、Socket.IO 重连、Runner 停止和 Worker offline。
- `tests/test_runner.py`：bundle 验证与确定性行为。

改动错误映射时至少增加一个失败 case，并确认成功 case 未被异常转换吞掉。
