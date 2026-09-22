# 测算 HTTP 合同测例（tests_http）

本目录与既有引擎数字测例目录 `app/tests`（`test_calc.py`）**错开**：

- `app/tests/test_calc.py`：直接调用 `app.engines.amortization.equal_payment_schedule`
  的纯数字测例（月供、首期利息、零利率、非法期数），**保持不动**。
- `tests_http/`（本目录）：经测试客户端 `fastapi.testclient.TestClient`
  对 `POST /api/schedule` 打的端到端 **HTTP 合同测例**。

## 覆盖路径

```
TestClient(ASGI)
  └─ app.routers.schedule.post_schedule
       ├─ app.schemas.schedule.ScheduleRequest   （Pydantic 入参校验，非法输入 422）
       └─ app.services.mortgage_service.MortgageService.schedule
            ├─ app.engines.amortization.equal_payment_schedule
            └─ app.repositories.runs.insert      （persist=true 时写 SQLite calc_runs）
```

夹具（见 `conftest.py`）在导入应用前把 `DATA_DIR` 指到临时目录，
启动应用时执行 `seed.init_db` 建表与种子数据，测试写入不污染开发库。

## 用例清单（test_schedule_contract.py）

| 用例 | 合同断言 |
| --- | --- |
| `test_valid_schedule_returns_fields_and_identity`（3.5%/360 期、0%/12 期两组参数） | 200；必含 `run_id`、`monthly_payment`、`total_interest`、`total_payment`、`row_count`、`preview`；`row_count` 等于期数；`preview` 行数等于 `preview_rows`；**利息合计 + 本金 == 还款合计，误差 ≤ 0.01 元** |
| `test_persist_false_run_id_empty_and_count_unchanged` | `run_id` 为 null（或等价空值）；连续两次请求，`calc_runs` 条数保持不变 |
| `test_persist_true_run_id_present_and_count_increments` | `run_id` 有值；`calc_runs` 条数恰好加一 |
| `test_illegal_inputs_are_rejected_without_persistence`（本金 -1、期数 0 两组） | 返回 422 拒绝；且不写入任何运行记录（条数不变） |

失败消息均点名具体缺失字段（经 `require_fields`）或前后条数。

## 运行方式

```bash
cd backend
pip install -r requirements.txt          # httpx 为 TestClient 所需
python3 -m pytest app/tests tests_http   # 引擎数字测例 + HTTP 合同测例一起跑
```

## 口径说明

为支撑“一分钱口径恒等检查”，摊销引擎采用**月供按分固定、利息/本金按分逐期
结转、末期结清尾差**的口径：`total_payment - total_interest` 恰等于本金
（正常房贷参数下差额为 0.00 元）。月供与首期利息数字与原引擎一致，
`app/tests/test_calc.py` 的既有断言不受影响。
