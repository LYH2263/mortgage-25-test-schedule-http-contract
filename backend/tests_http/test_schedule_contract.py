"""测算 HTTP 合同测例：POST /api/schedule

覆盖路径：TestClient(ASGI) -> routers.schedule -> schemas.ScheduleRequest
校验 -> MortgageService.schedule -> engines 摊销计算 -> repositories.runs
落库（SQLite）。

合同要点：
1. 合法请求必须返回 monthly_payment / total_interest / total_payment /
   row_count / preview；且 利息合计 + 本金 == 还款合计（误差 <= 一分钱）。
2. persist=false：run_id 为空（null），连续两次 calc_runs 条数不变。
3. persist=true：run_id 有值，calc_runs 条数恰好加一。
4. 本金为负、期数为零：请求被拒绝（422），且不落任何运行记录。
"""
import pytest

from conftest import ONE_CENT, require_fields

ENDPOINT = "/api/schedule"
LEGAL_BODY = {
    "principal": 1_000_000,
    "annual_rate": 3.5,
    "months": 360,
    "persist": False,
    "preview_rows": 12,
}
REQUIRED_FIELDS = (
    "monthly_payment",
    "total_interest",
    "total_payment",
    "row_count",
    "preview",
)


@pytest.mark.parametrize(
    "principal,annual_rate,months,expect_payment",
    [
        (1_000_000, 3.5, 360, 4490.45),
        (120_000, 0.0, 12, 10000.0),
    ],
)
def test_valid_schedule_returns_fields_and_identity(
    client, principal, annual_rate, months, expect_payment
):
    body = {**LEGAL_BODY, "principal": principal,
            "annual_rate": annual_rate, "months": months}
    resp = client.post(ENDPOINT, json=body)
    assert resp.status_code == 200, f"合法请求应返回 200，实际 {resp.status_code}：{resp.text}"
    data = resp.json()

    # run_id 也必须出现在合同中（persist=false 时为 null）。
    require_fields(data, "run_id", *REQUIRED_FIELDS)

    assert data["monthly_payment"] == pytest.approx(expect_payment, abs=ONE_CENT), (
        f"月供应为 {expect_payment}，实际 {data['monthly_payment']}"
    )
    assert data["row_count"] == months, (
        f"row_count 应为期数 {months}，实际 {data['row_count']}（条数不符）"
    )
    assert isinstance(data["preview"], list) and len(data["preview"]) == body["preview_rows"], (
        f"preview 应含 {body['preview_rows']} 行，实际 {len(data['preview'])} 行（条数不符）"
    )
    assert data["preview"][0]["period"] == 1, "preview 首行 period 应为 1"

    # 利息合计 + 本金 == 还款合计，一分钱口径下的恒等检查。
    gap = round(data["total_interest"] + principal - data["total_payment"], 2)
    assert abs(gap) <= ONE_CENT, (
        f"恒等检查失败：利息合计 {data['total_interest']} + 本金 {principal} "
        f"与还款合计 {data['total_payment']} 相差 {gap} 元，超过一分钱口径"
    )


def test_persist_false_run_id_empty_and_count_unchanged(client, count_runs):
    before = count_runs()
    for seq in (1, 2):
        resp = client.post(ENDPOINT, json={**LEGAL_BODY, "persist": False})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        require_fields(data, "run_id", *REQUIRED_FIELDS)
        assert data["run_id"] in (None, ""), (
            f"persist=false 时 run_id 应为空，第 {seq} 次请求实际为 {data['run_id']!r}"
        )
        now_count = count_runs()
        assert now_count == before, (
            f"persist=false 第 {seq} 次请求后 calc_runs 条数由 {before} 变为 {now_count}"
            "（条数应保持不变，疑似误写入）"
        )


def test_persist_true_run_id_present_and_count_increments(client, count_runs):
    before = count_runs()
    resp = client.post(ENDPOINT, json={**LEGAL_BODY, "persist": True})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    require_fields(data, "run_id", *REQUIRED_FIELDS)
    assert data["run_id"], f"persist=true 时 run_id 应有值，实际为 {data['run_id']!r}"

    after = count_runs()
    assert after == before + 1, (
        f"persist=true 后 calc_runs 条数应加一：写入前 {before} 条，写入后 {after} 条（条数不符）"
    )


@pytest.mark.parametrize(
    "bad_body,offender",
    [
        ({**LEGAL_BODY, "principal": -1, "persist": False}, "principal"),
        ({**LEGAL_BODY, "months": 0, "persist": False}, "months"),
    ],
)
def test_illegal_inputs_are_rejected_without_persistence(
    client, count_runs, bad_body, offender
):
    before = count_runs()
    resp = client.post(ENDPOINT, json=bad_body)
    assert resp.status_code == 422, (
        f"非法字段 {offender} 的请求应被拒绝(422)，实际 {resp.status_code}：{resp.text}"
    )
    after = count_runs()
    assert after == before, (
        f"非法请求（{offender}）不应写入运行记录，calc_runs 条数却由 {before} 变为 {after}"
    )
