"""schedule 测算 HTTP 合同测例的公共夹具。

与既有引擎数字测例目录 app/tests 错开：这里走真实 ASGI 链路
（TestClient -> 路由 -> Pydantic 校验 -> MortgageService -> SQLite）。
数据库在导入应用前指到临时目录，测试写入不会污染开发库。
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

# 必须在导入 app.config / app.db 之前设置，DB_PATH 在导入时按 DATA_DIR 定值。
_TMP_DATA = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _TMP_DATA.name

from fastapi.testclient import TestClient  # noqa: E402

from app.db import connect  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    # 进入上下文时触发 startup 钩子（seed.init_db：建表 + 种子 1 条 calc_runs）。
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def count_runs():
    """返回实时统计 calc_runs 条数的可调用对象。"""

    def _count() -> int:
        conn = connect()
        try:
            return conn.execute("SELECT COUNT(*) AS c FROM calc_runs").fetchone()["c"]
        finally:
            conn.close()

    return _count


def require_fields(payload: dict, *fields: str) -> None:
    """断言必备字段齐全，失败消息点名具体缺失字段。"""
    missing = [f for f in fields if f not in payload]
    assert not missing, f"响应缺少字段 {missing}；实际返回字段：{sorted(payload)}"


ONE_CENT = 0.01
