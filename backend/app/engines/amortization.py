def equal_payment_schedule(principal: float, annual_rate: float, months: int) -> dict:
    P = float(principal)
    n = int(months)
    r = float(annual_rate) / 12.0 / 100.0
    if n <= 0:
        raise ValueError("months")
    if r == 0:
        pay = round(P / n, 2)
    else:
        pay = round(P * r * (1 + r) ** n / ((1 + r) ** n - 1), 2)
    rows = []
    bal = P
    for i in range(1, n + 1):
        interest = round(bal * r, 2)
        if i < n:
            # 月供按分取整，每期 payment = principal + interest 严格成立
            principal_part = round(pay - interest, 2)
            pay_i = pay
            bal = round(bal - principal_part, 2)
        else:
            # 末期承接取整残差：一次性还清剩余本金，保证本金合计等于贷款本金
            principal_part = round(bal, 2)
            pay_i = round(principal_part + interest, 2)
            bal = 0.0
        rows.append({
            "period": i,
            "payment": pay_i,
            "principal": principal_part,
            "interest": interest,
            "balance": bal,
        })
    total_payment = round(sum(x["payment"] for x in rows), 2)
    total_interest = round(sum(x["interest"] for x in rows), 2)
    return {
        "monthly_payment": pay,
        "total_interest": total_interest,
        "total_payment": total_payment,
        "rows": rows,
    }
