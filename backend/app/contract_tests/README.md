# schedule HTTP 合同测例（contract_tests）

本目录是 **POST `/api/schedule` 的 HTTP 合同测例**，与原有引擎数字测例
`app/tests/test_calc.py` 目录错开、互不替代：

| 目录 | 层次 | 测什么 |
| --- | --- | --- |
| `app/tests/`（原有，未改动用例） | 引擎纯函数 | 月供、首期利息、零利率、非法期数等**逐期数字** |
| `app/contract_tests/`（本目录，新增） | HTTP 接口 | 响应字段合同、一分钱口径恒等式、持久化条数、非法入参拒绝 |

所有用例通过 FastAPI `TestClient` **真实打 HTTP 接口**（非直接调函数），
并把 `DATA_DIR` 重定向到系统临时目录（见 `conftest.py`，在 import 应用前设置），
不读写开发库 `backend/data/app.db`。

## 运行

```bash
cd backend
pip install -r requirements.txt        # 含 httpx（TestClient 依赖）

# 只跑合同测例
python -m pytest app/contract_tests -v

# 连同原有引擎数字测例一起跑（原用例保持通过、未删除）
python -m pytest app/tests app/contract_tests -v
```

## 覆盖路径

每个请求都完整穿过以下链路，任何一层行为漂移都会被捕获：

```
POST /api/schedule
  -> app/routers/schedule.py        post_schedule 路由
  -> app/schemas/schedule.py        ScheduleRequest（Pydantic 校验：principal>0, months 1..600 …）
  -> app/services/mortgage_service.py  MortgageService.schedule（拼装响应、按 persist 决定落库）
  -> app/engines/amortization.py    equal_payment_schedule（等额本息逐期拆分）
  -> app/repositories/runs.py       insert（仅 persist=true 时写 calc_runs）
  -> SQLite                        calc_runs 表
```

## 用例清单

| 用例 | 断言要点 | 失败时点名 |
| --- | --- | --- |
| `test_legal_request_returns_full_contract` | 合法请求 200，且返回月供 `monthly_payment`、利息合计 `total_interest`、还款合计 `total_payment`、`row_count`、`preview` | 缺失的具体字段名 |
| `test_interest_plus_principal_equals_payment_within_one_fen`（5 组参数：标准/高利率/零利率/奇零数/仅一期） | `abs(total_interest + principal - total_payment) ≤ 0.01` 元 | 三项数值与实际误差 |
| `test_row_count_matches_months_and_preview_respects_preview_rows` | `row_count == months`；preview 条数 = `min(months, preview_rows)`；行字段 `period/payment/principal/interest/balance` 齐全且期次连续 | `row_count` 或 preview 条数 |
| `test_persist_false_writes_no_run_and_count_stable` | persist=false 时 `run_id` 为空（None）；**连续两次**调用后 `calc_runs` 条数与调用前完全一致 | 前后条数对比 |
| `test_persist_true_returns_run_id_and_inserts_one_row` | persist=true 时 `run_id` 有值；`calc_runs` 条数**恰好加一** | 前后条数与差值 |
| `test_negative_principal_rejected` | 本金为负返回 4xx，错误体点名 `principal`，且不落库 | 状态码、字段名、条数 |
| `test_zero_months_rejected` | 期数为零返回 4xx，错误体点名 `months`，且不落库 | 状态码、字段名、条数 |

> 说明：表中“失败时点名”指断言消息会带上具体缺失字段或前后条数（如
> “响应缺少利息合计字段 total_interest …”“调用前条数 1，调用后条数 2（差值 1）”），
> 便于直接定位。

## 配套引擎修正（为满足一分钱恒等口径）

原引擎逐期独立四舍五入，末期不做找平，导致 `利息合计 + 本金` 与
`还款合计` 在标准贷款（100 万 / 3.5% / 360 期）上相差约 **1.12 元**，
无法通过一分钱口径恒等检查。`app/engines/amortization.py` 按常见贷款
口径做了**分位找平**：

- 月供先按分取整，每期保证 `payment == principal + interest`；
- 末期一次性还清剩余本金（承接取整残差），保证“本金合计 == 贷款本金”；
- `total_interest` 改为逐期利息求和（原为未取整利息求和）。

修正后 5000 组随机贷款（本金 1000–500 万、利率 0–12%、期数 1–600）恒等
误差均为 0.00 元；原有数字断言（月供 4490.45、首期利息 2916.67、
零利率月供 10000.0、期数 0 抛 `ValueError`）全部保持通过。
