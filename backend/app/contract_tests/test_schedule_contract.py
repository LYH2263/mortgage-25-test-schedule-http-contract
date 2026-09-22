"""POST /api/schedule 的 HTTP 合同测例（经测试客户端真实打接口）。

覆盖路径：
  HTTP POST /api/schedule
    -> routers/schedule.post_schedule
    -> schemas/schedule.ScheduleRequest（Pydantic 校验）
    -> services/mortgage_service.MortgageService.schedule
    -> engines/amortization.equal_payment_schedule
    -> repositories/runs.insert（仅 persist=true）
    -> SQLite calc_runs

本文件只验“合同”：响应字段、一分钱口径恒等式、持久化条数、非法入参拒绝。
引擎逐期数字仍由 app/tests/test_calc.py 覆盖，本套件不替代、不删除它。
"""
import pytest

# 合法请求必须返回的字段：月供 / 利息合计 / 还款合计 / row_count / preview
REQUIRED_FIELDS = {
    "monthly_payment": "月供",
    "total_interest": "利息合计",
    "total_payment": "还款合计",
    "row_count": "总期数",
    "preview": "还款表预览",
}

LEGAL_BODY = {"principal": 1_000_000, "annual_rate": 3.5, "months": 360}

ONE_FEN = 0.01  # 一分钱口径


def _assert_required_fields(data: dict) -> None:
    for field, label in REQUIRED_FIELDS.items():
        assert field in data, (
            f"响应缺少{label}字段 {field}，实际返回字段：{sorted(data.keys())}"
        )


def test_legal_request_returns_full_contract(client):
    """合法请求必须返回月供、利息合计、还款合计、row_count 与 preview。"""
    resp = client.post("/api/schedule", json={**LEGAL_BODY, "persist": False})
    assert resp.status_code == 200, f"合法请求应返回 200，实际 {resp.status_code}：{resp.text}"
    data = resp.json()
    _assert_required_fields(data)

    assert isinstance(data["monthly_payment"], (int, float)) and data["monthly_payment"] > 0, (
        f"月供 monthly_payment 应为正数，实际 {data['monthly_payment']!r}"
    )
    assert isinstance(data["total_interest"], (int, float)) and data["total_interest"] >= 0, (
        f"利息合计 total_interest 应为非负数，实际 {data['total_interest']!r}"
    )
    assert isinstance(data["total_payment"], (int, float)) and data["total_payment"] > 0, (
        f"还款合计 total_payment 应为正数，实际 {data['total_payment']!r}"
    )
    assert data["row_count"] == LEGAL_BODY["months"], (
        f"row_count 应等于请求期数 {LEGAL_BODY['months']}，实际 {data['row_count']}"
    )
    assert isinstance(data["preview"], list) and data["preview"], (
        f"preview 应为非空数组，实际 {data['preview']!r}"
    )


@pytest.mark.parametrize(
    "principal,annual_rate,months",
    [
        (1_000_000, 3.5, 360),   # 标准长期贷款
        (800_000, 6.8, 240),     # 高利率
        (120_000, 0.0, 12),      # 零利率
        (123_456.78, 4.567, 77), # 非整本金/利率、奇数期
        (50_000, 3.1, 1),        # 仅一期
    ],
)
def test_interest_plus_principal_equals_payment_within_one_fen(client, principal, annual_rate, months):
    """利息合计 + 本金 == 还款合计，误差不超过一分钱。"""
    resp = client.post(
        "/api/schedule",
        json={"principal": principal, "annual_rate": annual_rate, "months": months, "persist": False},
    )
    assert resp.status_code == 200, f"合法请求应返回 200，实际 {resp.status_code}：{resp.text}"
    data = resp.json()
    _assert_required_fields(data)

    delta = abs(data["total_interest"] + principal - data["total_payment"])
    assert delta <= ONE_FEN + 1e-9, (
        f"利息合计({data['total_interest']}) + 本金({principal}) "
        f"与还款合计({data['total_payment']}) 相差 {delta:.4f} 元，超过一分钱口径"
    )


def test_row_count_matches_months_and_preview_respects_preview_rows(client):
    """row_count 等于期数；preview 截断为 min(months, preview_rows)，行结构完整。"""
    resp = client.post(
        "/api/schedule",
        json={"principal": 500_000, "annual_rate": 4.2, "months": 300, "persist": False, "preview_rows": 10},
    )
    assert resp.status_code == 200, f"合法请求应返回 200，实际 {resp.status_code}：{resp.text}"
    data = resp.json()
    _assert_required_fields(data)

    assert data["row_count"] == 300, f"row_count 应为 300，实际 {data['row_count']}"
    assert len(data["preview"]) == 10, (
        f"preview 条数应等于 preview_rows=10，实际 {len(data['preview'])}"
    )

    row_keys = {"period", "payment", "principal", "interest", "balance"}
    first = data["preview"][0]
    missing = row_keys - set(first.keys())
    assert not missing, f"preview 首行缺少字段：{sorted(missing)}，实际字段 {sorted(first.keys())}"
    assert [r["period"] for r in data["preview"]] == list(range(1, 11)), (
        "preview 期次应从 1 连续编号"
    )

    # 请求期数少于 preview_rows 时，preview 不得多于实际行数
    short = client.post(
        "/api/schedule",
        json={"principal": 10_000, "annual_rate": 3.0, "months": 6, "persist": False, "preview_rows": 12},
    ).json()
    assert short["row_count"] == 6, f"短期贷款 row_count 应为 6，实际 {short['row_count']}"
    assert len(short["preview"]) == 6, (
        f"preview 条数应截断为实际期数 6，实际 {len(short['preview'])}"
    )


def test_persist_false_writes_no_run_and_count_stable(client, run_count):
    """persist 为假：run_id 为空（None），连续两次后 calc_runs 条数不变。"""
    before = run_count()

    first = client.post("/api/schedule", json={**LEGAL_BODY, "persist": False})
    assert first.status_code == 200, f"合法请求应返回 200，实际 {first.status_code}：{first.text}"
    first_data = first.json()
    _assert_required_fields(first_data)
    assert not first_data["run_id"], (
        f"persist=false 时 run_id 应为空/None，实际 {first_data['run_id']!r}"
    )
    after_first = run_count()
    assert after_first == before, (
        f"persist=false 不应写入计算记录：调用前条数 {before}，第一次调用后条数 {after_first}"
    )

    second = client.post("/api/schedule", json={**LEGAL_BODY, "persist": False})
    assert second.status_code == 200, f"合法请求应返回 200，实际 {second.status_code}：{second.text}"
    assert not second.json()["run_id"], (
        f"persist=false 时 run_id 应为空/None，实际 {second.json()['run_id']!r}"
    )
    after_second = run_count()
    assert after_second == before, (
        f"persist=false 连续两次后条数应保持 {before} 不变，实际条数 {after_second}（多写 {after_second - before} 条）"
    )


def test_persist_true_returns_run_id_and_inserts_one_row(client, run_count):
    """persist 为真：run_id 有值，calc_runs 条数恰好加一，且落库结果含月供。"""
    before = run_count()

    resp = client.post("/api/schedule", json={**LEGAL_BODY, "persist": True})
    assert resp.status_code == 200, f"合法请求应返回 200，实际 {resp.status_code}：{resp.text}"
    data = resp.json()
    _assert_required_fields(data)

    run_id = data["run_id"]
    assert run_id, f"persist=true 时 run_id 应有值，实际 {run_id!r}"

    after = run_count()
    assert after == before + 1, (
        f"persist=true 应恰好写入 1 条计算记录：调用前条数 {before}，调用后条数 {after}（差值 {after - before}）"
    )


def test_negative_principal_rejected(client, run_count):
    """本金为负必须被拒绝（4xx），且不得产生计算记录。"""
    before = run_count()
    resp = client.post(
        "/api/schedule",
        json={"principal": -1, "annual_rate": 3.5, "months": 360, "persist": True},
    )
    assert 400 <= resp.status_code < 500, (
        f"本金为负必须被拒绝（期望 4xx），实际状态码 {resp.status_code}：{resp.text}"
    )
    assert "principal" in resp.text, (
        f"拒绝消息应点名非法字段 principal，实际响应：{resp.text}"
    )
    after = run_count()
    assert after == before, (
        f"非法请求不得写入计算记录：请求前条数 {before}，请求后条数 {after}"
    )


def test_zero_months_rejected(client, run_count):
    """期数为零必须被拒绝（4xx），且不得产生计算记录。"""
    before = run_count()
    resp = client.post(
        "/api/schedule",
        json={"principal": 1_000_000, "annual_rate": 3.5, "months": 0, "persist": True},
    )
    assert 400 <= resp.status_code < 500, (
        f"期数为零必须被拒绝（期望 4xx），实际状态码 {resp.status_code}：{resp.text}"
    )
    assert "months" in resp.text, (
        f"拒绝消息应点名非法字段 months，实际响应：{resp.text}"
    )
    after = run_count()
    assert after == before, (
        f"非法请求不得写入计算记录：请求前条数 {before}，请求后条数 {after}"
    )
