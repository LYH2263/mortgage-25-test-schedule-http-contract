def equal_payment_schedule(principal: float, annual_rate: float, months: int) -> dict:
    P = float(principal)
    n = int(months)
    r = float(annual_rate) / 12.0 / 100.0
    if n <= 0:
        raise ValueError("months")
    if r == 0:
        pay = P / n
    else:
        pay = P * r * (1 + r) ** n / ((1 + r) ** n - 1)
    # 月供先按分取整并在全周期内固定，尾差全部压入末期；
    # 利息与本金均按上期末余额（分）口径逐期结转，
    # 保证 利息合计 + 本金 = 还款合计（一分钱口径恒等）。
    pay = round(pay, 2)
    rows = []
    bal = round(P, 2)
    interest_sum = 0.0
    for i in range(1, n + 1):
        interest = round(bal * r, 2)
        if i == n:
            principal_part = bal
            pay_i = round(principal_part + interest, 2)
        else:
            pay_i = pay
            principal_part = round(pay_i - interest, 2)
        bal = round(bal - principal_part, 2)
        interest_sum = round(interest_sum + interest, 2)
        rows.append({
            "period": i,
            "payment": round(pay_i, 2),
            "principal": round(principal_part, 2),
            "interest": round(interest, 2),
            "balance": round(bal, 2),
        })
    return {
        "monthly_payment": pay,
        "total_interest": interest_sum,
        "total_payment": round(sum(x["payment"] for x in rows), 2),
        "rows": rows,
    }
